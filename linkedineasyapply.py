import time, random, csv, pyautogui, traceback, os, re, argparse, json, sys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from datetime import date, datetime
from itertools import product
from pypdf import PdfReader
from openai import OpenAI
from selenium import webdriver

def parse_args():
    parser = argparse.ArgumentParser(description='LinkedIn Easy Apply Bot')
    parser.add_argument('--strict-position', action='store_true',
                      help='Use strict position search (exact matches only)')
    return parser.parse_args()

class AIResponseGenerator:
    def __init__(self, api_key, personal_info, experience, languages, resume_path, text_resume_path=None, debug=False):
        self.personal_info = personal_info
        self.experience = experience
        self.languages = languages
        self.pdf_resume_path = resume_path
        self.text_resume_path = text_resume_path
        self._resume_content = None
        self._client = OpenAI(api_key=api_key) if api_key else None
        self.debug = debug
    @property
    def resume_content(self):
        if self._resume_content is None:
            # First try to read from text resume if available
            if self.text_resume_path:
                try:
                    with open(self.text_resume_path, 'r', encoding='utf-8') as f:
                        self._resume_content = f.read()
                        print("Successfully loaded text resume")
                        return self._resume_content
                except Exception as e:
                    print(f"Could not read text resume: {str(e)}")

            # Fall back to PDF resume if text resume fails or isn't available
            try:
                content = []
                reader = PdfReader(self.pdf_resume_path)
                for page in reader.pages:
                    content.append(page.extract_text())
                self._resume_content = "\n".join(content)
                print("Successfully loaded PDF resume")
            except Exception as e:
                print(f"Could not extract text from resume PDF: {str(e)}")
                self._resume_content = ""
        return self._resume_content

    def _build_context(self):
        return f"""
        Personal Information:
        - Name: {self.personal_info['First Name']} {self.personal_info['Last Name']}
        - Current Role: {self.experience.get('currentRole', '')}
        - Skills: {', '.join(self.experience.keys())}
        - Languages: {', '.join(f'{lang}: {level}' for lang, level in self.languages.items())}
        - Professional Summary: {self.personal_info.get('MessageToManager', '')}

        Resume Content (Give the greatest weight to this information, if specified):
        {self.resume_content}
        """

    def generate_response(self, question_text, response_type="text", options=None, max_tokens=100):
        """
        Generate a response using OpenAI's API

        Args:
            question_text: The application question to answer
            response_type: "text", "numeric", or "choice"
            options: For "choice" type, a list of tuples containing (index, text) of possible answers
            max_tokens: Maximum length of response

        Returns:
            - For text: Generated text response or None
            - For numeric: Integer value or None
            - For choice: Integer index of selected option or None
        """
        if not self._client:
            return None

        try:
            context = self._build_context()

            system_prompt = {
                "text": "You are a helpful assistant answering job application questions professionally and concisely. Use the candidate's background information and resume to personalize responses.",
                "numeric": "You are a helpful assistant providing numeric answers to job application questions. Based on the candidate's experience, provide a single number as your response. No explanation needed.",
                "choice": "You are a helpful assistant selecting the most appropriate answer choice for job application questions. Based on the candidate's background, select the best option by returning only its index number. No explanation needed."
            }[response_type]

            user_content = f"Using this candidate's background and resume:\n{context}\n\nPlease answer this job application question: {question_text}"
            if response_type == "choice" and options:
                options_text = "\n".join([f"{idx}: {text}" for idx, text in options])
                user_content += f"\n\nSelect the most appropriate answer by providing its index number from these options:\n{options_text}"

            response = self._client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=max_tokens,
                temperature=0.7
            )

            answer = response.choices[0].message.content.strip()
            print(f"AI response: {answer}")  # TODO: Put logging behind a debug flag

            if response_type == "numeric":
                # Extract first number from response
                numbers = re.findall(r'\d+', answer)
                if numbers:
                    return int(numbers[0])
                return 0
            elif response_type == "choice":
                # Extract the index number from the response
                numbers = re.findall(r'\d+', answer)
                if numbers and options:
                    index = int(numbers[0])
                    # Ensure index is within valid range
                    if 0 <= index < len(options):
                        return index
                return None  # Return None if the index is not within the valid range

            return answer

        except Exception as e:
            print(f"Error using AI to generate response: {str(e)}")
            return None

    def evaluate_job_fit(self, job_title, job_description):
        """
        Evaluate whether a job is worth applying to based on the candidate's experience and the job requirements

        Args:
            job_title: The title of the job posting
            job_description: The full job description text

        Returns:
            bool: True if should apply, False if should skip
        """
        if not self._client:
            return True  # Proceed with application if AI not available

        try:
            context = self._build_context()

            system_prompt = """You are evaluating job fit for technical roles.
            Recommend APPLY if:
            - Candidate meets 65 percent of the core requirements
            - Experience gap is 2 years or less
            - Has relevant transferable skills

            Return SKIP if:
            - Experience gap is greater than 2 years
            - Missing multiple core requirements
            - Role is clearly more senior
            - The role is focused on an uncommon technology or skill that is required and that the candidate does not have experience with
            - The role is a leadership role or a role that requires managing people and the candidate has no experience leading or managing people

            """
            #Consider the candidate's education level when evaluating whether they meet the core requirements. Having higher education than required should allow for greater flexibility in the required experience.

            if self.debug:
                system_prompt += """
                You are in debug mode. Return a detailed explanation of your reasoning for each requirement.

                Return APPLY or SKIP followed by a brief explanation.

                Format response as: APPLY/SKIP: [brief reason]"""
            else:
                system_prompt += """Return only APPLY or SKIP."""

            response = self._client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Job: {job_title}\n{job_description}\n\nCandidate:\n{context}"}
                ],
                max_tokens=250 if self.debug else 1,  # Allow more tokens when debug is enabled
                temperature=0.2  # Lower temperature for more consistent decisions
            )

            answer = response.choices[0].message.content.strip()
            print(f"AI evaluation: {answer}")
            return answer.upper().startswith('A')  # True for APPLY, False for SKIP

        except Exception as e:
            print(f"Error evaluating job fit: {str(e)}")
            return True  # Proceed with application if evaluation fails

class LinkedinEasyApply:
    def __init__(self, parameters, driver):
        self.browser = driver
        self.email = parameters['email']
        self.password = parameters['password']
        self.openai_api_key = parameters.get('openaiApiKey', '')  # Get API key with empty default
        self.disable_lock = parameters['disableAntiLock']
        self.company_blacklist = parameters.get('companyBlacklist', []) or []
        self.title_blacklist = parameters.get('titleBlacklist', []) or []
        self.use_llm = parameters.get('useLLM', True)  # Default to using LLM if not specified
        self.debug = parameters.get('debug', False)  # Default to not debug mode if not specified
        self.strict_mode = parameters.get('strictMode', False)  # Default to not strict mode if not specified
        self.strict_search = parameters.get('strictSearch', False)  # Default to not strict search if not specified
        self.poster_blacklist = parameters.get('posterBlacklist', []) or []
        self.positions = parameters.get('positions', [])
        self.locations = parameters.get('locations', [])
        self.residency = parameters.get('residentStatus', [])
        self.base_search_url = self.get_base_search_url(parameters)
        self.seen_jobs = []
        self.file_name = "output"
        self.unprepared_questions_file_name = "unprepared_questions"
        self.output_file_directory = parameters['outputFileDirectory']
        self.resume_dir = parameters['uploads']['resume']
        self.text_resume = parameters.get('textResume', '')
        if 'coverLetter' in parameters['uploads']:
            self.cover_letter_dir = parameters['uploads']['coverLetter']
        else:
            self.cover_letter_dir = ''
        self.checkboxes = parameters.get('checkboxes', [])
        self.university_gpa = parameters['universityGpa']
        self.salary_minimum = parameters['salaryMinimum']
        self.notice_period = int(parameters['noticePeriod'])
        self.languages = parameters.get('languages', [])
        self.experience = parameters.get('experience', [])
        self.personal_info = parameters.get('personalInfo', [])
        self.eeo = parameters.get('eeo', [])
        self.experience_default = int(self.experience['default'])
        self.evaluate_job_fit = parameters.get('evaluateJobFit', True)

        # Initialize AI response generator only if LLM is enabled and API key is provided
        self.ai_generator = None
        if self.use_llm and self.openai_api_key:
            self.ai_generator = AIResponseGenerator(
                api_key=self.openai_api_key,
                personal_info=self.personal_info,
                experience=self.experience,
                languages=self.languages,
                resume_path=self.resume_dir,
                text_resume_path=self.text_resume,
                debug=self.debug
            )
        elif self.use_llm and not self.openai_api_key:
            print("Warning: LLM is enabled but no OpenAI API key provided. Falling back to predefined responses.")
            self.use_llm = False

    def login(self):
        try:
            # Check if the "chrome_bot" directory exists
            print("Attempting to restore previous session...")
            if os.path.exists("chrome_bot"):
                self.browser.get("https://www.linkedin.com/feed/")
                time.sleep(random.uniform(5, 10))

                # Check if the current URL is the feed page
                if self.browser.current_url != "https://www.linkedin.com/feed/":
                    print("Feed page not loaded, proceeding to login.")
                    self.load_login_page_and_login()
            else:
                print("No session found, proceeding to login.")
                self.load_login_page_and_login()

        except TimeoutException:
            print("Timeout occurred, checking for security challenges...")
            self.security_check()
            # raise Exception("Could not login!")

    def security_check(self):
        current_url = self.browser.current_url
        page_source = self.browser.page_source

        if '/checkpoint/challenge/' in current_url or 'security check' in page_source or 'quick verification' in page_source:
            input("Please complete the security check and press enter on this console when it is done.")
            time.sleep(random.uniform(5.5, 10.5))

    def load_login_page_and_login(self):
        self.browser.get("https://www.linkedin.com/login")

        # Wait for the username field to be present
        WebDriverWait(self.browser, 10).until(
            EC.presence_of_element_located((By.ID, "username"))
        )

        self.browser.find_element(By.ID, "username").send_keys(self.email)
        self.browser.find_element(By.ID, "password").send_keys(self.password)
        self.browser.find_element(By.CSS_SELECTOR, ".btn__primary--large").click()

        # Wait for the feed page to load after login
        WebDriverWait(self.browser, 10).until(
            EC.url_contains("https://www.linkedin.com/feed/")
        )

        time.sleep(random.uniform(5, 10))

    def start_applying(self):
        searches = list(product(self.positions, self.locations))
        random.shuffle(searches)

        page_sleep = 0
        minimum_time = 60 * 2  # minimum time bot should run before taking a break
        minimum_page_time = time.time() + minimum_time

        for (position, location) in searches:
            location_url = "&location=" + location
            job_page_number = -1

            print("Starting the search for " + position + " in " + location + ".")

            try:
                while True:
                    page_sleep += 1
                    job_page_number += 1
                    print("Going to job page " + str(job_page_number))
                    self.next_job_page(position, location_url, job_page_number)
                    time.sleep(random.uniform(1.5, 3.5))
                    print("Starting the application process for this page...")
                    self.apply_jobs(location)
                    print("Job applications on this page have been successfully completed.")

                    time_left = minimum_page_time - time.time()
                    if time_left > 0:
                        print("Sleeping for " + str(time_left) + " seconds.")
                        time.sleep(time_left)
                        minimum_page_time = time.time() + minimum_time
                    if page_sleep % 5 == 0:
                        sleep_time = random.randint(180, 300)  # Changed from 500, 900 {seconds}
                        print("Sleeping for " + str(sleep_time / 60) + " minutes.")
                        time.sleep(sleep_time)
                        page_sleep += 1
            except:
                traceback.print_exc()
                pass

            time_left = minimum_page_time - time.time()
            if time_left > 0:
                print("Sleeping for " + str(time_left) + " seconds.")
                time.sleep(time_left)
                minimum_page_time = time.time() + minimum_time
            if page_sleep % 5 == 0:
                sleep_time = random.randint(500, 900)
                print("Sleeping for " + str(sleep_time / 60) + " minutes.")
                time.sleep(sleep_time)
                page_sleep += 1

    def apply_jobs(self, location):
        no_jobs_text = ""
        try:
            no_jobs_element = self.browser.find_element(By.CLASS_NAME,
                                                        'jobs-search-two-pane__no-results-banner--expand')
            no_jobs_text = no_jobs_element.text
        except:
            pass
        if 'No matching jobs found' in no_jobs_text:
            raise Exception("No more jobs on this page.")

        if 'unfortunately, things are' in self.browser.page_source.lower():
            raise Exception("No more jobs on this page.")

        job_results_header = ""
        maybe_jobs_crap = ""
        job_results_header = self.browser.find_element(By.CLASS_NAME, "jobs-search-results-list__text")
        maybe_jobs_crap = job_results_header.text

        if 'Jobs you may be interested in' in maybe_jobs_crap:
            raise Exception("Nothing to do here, moving forward...")

        try:
            # TODO: Can we simply use class name scaffold-layout__list for the scroll (necessary to show all li in the dom?)? Does it need to be the ul within the scaffold list?
            #      Then we can simply get all the li scaffold-layout__list-item elements within it for the jobs

            # Define the XPaths for potentially different regions
            xpath_region1 = "/html/body/div[6]/div[3]/div[4]/div/div/main/div/div[2]/div[1]/div"
            xpath_region2 = "/html/body/div[5]/div[3]/div[4]/div/div/main/div/div[2]/div[1]/div"
            job_list = []

            # Attempt to locate the element using XPaths
            try:
                job_results = self.browser.find_element(By.XPATH, xpath_region1)
                ul_xpath = "/html/body/div[6]/div[3]/div[4]/div/div/main/div/div[2]/div[1]/div/ul"
                ul_element = self.browser.find_element(By.XPATH, ul_xpath)
                ul_element_class = ul_element.get_attribute("class").split()[0]
                print(f"Found using xpath_region1 and detected ul_element as {ul_element_class} based on {ul_xpath}")

            except NoSuchElementException:
                job_results = self.browser.find_element(By.XPATH, xpath_region2)
                ul_xpath = "/html/body/div[5]/div[3]/div[4]/div/div/main/div/div[2]/div[1]/div/ul"
                ul_element = self.browser.find_element(By.XPATH, ul_xpath)
                ul_element_class = ul_element.get_attribute("class").split()[0]
                print(f"Found using xpath_region2 and detected ul_element as {ul_element_class} based on {ul_xpath}")

            # Extract the random class name dynamically
            random_class = job_results.get_attribute("class").split()[0]
            print(f"Random class detected: {random_class}")

            # Use the detected class name to find the element
            job_results_by_class = self.browser.find_element(By.CSS_SELECTOR, f".{random_class}")
            print(f"job_results: {job_results_by_class}")
            print("Successfully located the element using the random class name.")

            # Scroll logic (currently disabled for testing)
            self.scroll_slow(job_results_by_class)  # Scroll down
            self.scroll_slow(job_results_by_class, step=300, reverse=True)  # Scroll up

            # Find job list elements
            job_list = self.browser.find_elements(By.CLASS_NAME, ul_element_class)[0].find_elements(By.CLASS_NAME, 'scaffold-layout__list-item')
            print(f"Found {len(job_list)} jobs on this page")

            if len(job_list) == 0:
                raise Exception("No more jobs on this page.")  # TODO: Seemed to encounter an error where we ran out of jobs and didn't go to next page, perhaps because I didn't have scrolling on?

        except NoSuchElementException:
            print("No job results found using the specified XPaths or class.")

        except Exception as e:
            print(f"An unexpected error occurred: {e}")

        for job_tile in job_list:
            job_title, company, poster, job_location, apply_method, link = "", "", "", "", "", ""

            try:
                ## patch to incorporate new 'verification' crap by LinkedIn
                # job_title = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title').text # original code
                job_title_element = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title--link')
                job_title = job_title_element.find_element(By.TAG_NAME, 'strong').text

                link = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title--link').get_attribute('href').split('?')[0]
            except:
                pass
            try:
                # company = job_tile.find_element(By.CLASS_NAME, 'job-card-container__primary-description').text # original code
                company = job_tile.find_element(By.CLASS_NAME, 'artdeco-entity-lockup__subtitle').text
            except:
                pass
            try:
                # get the name of the person who posted for the position, if any is listed
                hiring_line = job_tile.find_element(By.XPATH, '//span[contains(.,\' is hiring for this\')]')
                hiring_line_text = hiring_line.text
                name_terminating_index = hiring_line_text.find(' is hiring for this')
                if name_terminating_index != -1:
                    poster = hiring_line_text[:name_terminating_index]
            except:
                pass
            try:
                job_location = job_tile.find_element(By.CLASS_NAME, 'job-card-container__metadata-item').text
            except:
                pass
            try:
                apply_method = job_tile.find_element(By.CLASS_NAME, 'job-card-container__apply-method').text
            except:
                pass

            contains_blacklisted_keywords = False
            job_title_parsed = job_title.lower().split(' ')

            for word in self.title_blacklist:
                if word.lower() in job_title_parsed:
                    contains_blacklisted_keywords = True
                    break

            if company.lower() not in [word.lower() for word in self.company_blacklist] and \
                    poster.lower() not in [word.lower() for word in self.poster_blacklist] and \
                    contains_blacklisted_keywords is False and link not in self.seen_jobs:
                try:
                    # Click the job to load description
                    max_retries = 3
                    retries = 0
                    while retries < max_retries:
                        try:
                            # TODO: This is throwing an exception when running out of jobs on a page
                            job_el = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title--link')
                            job_el.click()
                            break
                        except StaleElementReferenceException:
                            retries += 1
                            continue

                    time.sleep(random.uniform(3, 5))

                    # TODO: Check if the job is already applied or the application has been reached
                    # "You've reached the Easy Apply application limit for today. Save this job and come back tomorrow to continue applying."
                    # Do this before evaluating job fit to save on API calls

                    if self.evaluate_job_fit:
                        try:
                            # Get job description
                            job_description = self.browser.find_element(
                                By.ID, 'job-details'
                            ).text

                            # Evaluate if we should apply
                            if not self.ai_generator.evaluate_job_fit(job_title, job_description):
                                print("Skipping application: Job requirements not aligned with candidate profile per AI evaluation.")
                                continue
                        except:
                            print("Could not load job description")

                    try:
                        done_applying = self.apply_to_job()
                        if done_applying:
                            print(f"Application sent to {company} for the position of {job_title}.")
                        else:
                            print(f"An application for a job at {company} has been submitted earlier.")
                    except:
                        temp = self.file_name
                        self.file_name = "failed"
                        print("Failed to apply to job. Please submit a bug report with this link: " + link)
                        try:
                            self.write_to_file(company, job_title, link, job_location, location)
                        except:
                            pass
                        self.file_name = temp
                        print(f'updated {temp}.')

                    try:
                        self.write_to_file(company, job_title, link, job_location, location)
                    except Exception:
                        print(
                            f"Unable to save the job information in the file. The job title {job_title} or company {company} cannot contain special characters,")
                        traceback.print_exc()
                except:
                    traceback.print_exc()
                    print(f"Could not apply to the job in {company}")
                    pass
            else:
                print(f"Job for {company} by {poster} contains a blacklisted word {word}.")

            self.seen_jobs += link

    def apply_to_job(self):
        easy_apply_button = None

        try:
            easy_apply_button = self.browser.find_element(By.CLASS_NAME, 'jobs-apply-button')
        except:
            return False

        try:
            job_description_area = self.browser.find_element(By.ID, "job-details")
            print (f"{job_description_area}")
            self.scroll_slow(job_description_area, end=1600)
            self.scroll_slow(job_description_area, end=1600, step=400, reverse=True)
        except:
            pass

        print("Starting the job application...")
        easy_apply_button.click()

        button_text = ""
        submit_application_text = 'submit application'
        while submit_application_text not in button_text.lower():
            try:
                self.fill_up()
                next_button = self.browser.find_element(By.CLASS_NAME, "artdeco-button--primary")
                button_text = next_button.text.lower()
                if submit_application_text in button_text:
                    try:
                        self.unfollow()
                    except:
                        print("Failed to unfollow company.")
                time.sleep(random.uniform(1.5, 2.5))
                next_button.click()
                time.sleep(random.uniform(3.0, 5.0))

                # Newer error handling
                error_messages = [
                    'enter a valid',
                    'enter a decimal',
                    'Enter a whole number'
                    'Enter a whole number between 0 and 99',
                    'file is required',
                    'whole number',
                    'make a selection',
                    'select checkbox to proceed',
                    'saisissez un numéro',
                    '请输入whole编号',
                    '请输入decimal编号',
                    '长度超过 0.0',
                    'Numéro de téléphone',
                    'Introduce un número de whole entre',
                    'Inserisci un numero whole compreso',
                    'Preguntas adicionales',
                    'Insira um um número',
                    'Cuántos años'
                    'use the format',
                    'A file is required',
                    '请选择',
                    '请 选 择',
                    'Inserisci',
                    'wholenummer',
                    'Wpisz liczb',
                    'zakresu od',
                    'tussen'
                ]

                if any(error in self.browser.page_source.lower() for error in error_messages):
                    raise Exception("Failed answering required questions or uploading required files.")
            except:
                traceback.print_exc()
                self.browser.find_element(By.CLASS_NAME, 'artdeco-modal__dismiss').click()
                time.sleep(random.uniform(3, 5))
                self.browser.find_elements(By.CLASS_NAME, 'artdeco-modal__confirm-dialog-btn')[0].click()
                time.sleep(random.uniform(3, 5))
                raise Exception("Failed to apply to job!")

        closed_notification = False
        time.sleep(random.uniform(3, 5))
        try:
            self.browser.find_element(By.CLASS_NAME, 'artdeco-modal__dismiss').click()
            closed_notification = True
        except:
            pass
        try:
            self.browser.find_element(By.CLASS_NAME, 'artdeco-toast-item__dismiss').click()
            closed_notification = True
        except:
            pass
        try:
            self.browser.find_element(By.CSS_SELECTOR, 'button[data-control-name="save_application_btn"]').click()
            closed_notification = True
        except:
            pass

        time.sleep(random.uniform(3, 5))

        if closed_notification is False:
            raise Exception("Could not close the applied confirmation window!")

        return True

    def home_address(self, form):
        print("Trying to fill up home address fields")
        try:
            groups = form.find_elements(By.CLASS_NAME, 'jobs-easy-apply-form-section__grouping')
            if len(groups) > 0:
                for group in groups:
                    lb = group.find_element(By.TAG_NAME, 'label').text.lower()
                    input_field = group.find_element(By.TAG_NAME, 'input')
                    if 'street' in lb:
                        self.enter_text(input_field, self.personal_info['Street address'])
                    elif 'city' in lb:
                        self.enter_text(input_field, self.personal_info['City'])
                        time.sleep(3)
                        input_field.send_keys(Keys.DOWN)
                        input_field.send_keys(Keys.RETURN)
                    elif 'zip' in lb or 'zip / postal code' in lb or 'postal' in lb:
                        self.enter_text(input_field, self.personal_info['Zip'])
                    elif 'state' in lb or 'province' in lb:
                        self.enter_text(input_field, self.personal_info['State'])
                    else:
                        pass
        except:
            pass

    def get_answer(self, question):
        if self.checkboxes[question]:
            return 'yes'
        else:
            return 'no'

    def additional_questions(self, form):
        print("Trying to fill up additional questions")

        questions = form.find_elements(By.CLASS_NAME, 'fb-dash-form-element')
        for question in questions:
            try:
                # Radio check
                radio_fieldset = question.find_element(By.TAG_NAME, 'fieldset')
                question_span = radio_fieldset.find_element(By.CLASS_NAME, 'fb-dash-form-element__label').find_elements(By.TAG_NAME, 'span')[0]
                radio_text = question_span.text.lower()  # Convert question to lowercase
                print(f"Radio question text: {radio_text}")

                radio_labels = radio_fieldset.find_elements(By.TAG_NAME, 'label')
                # Store both original text and lowercase version for matching
                radio_options = [(i, text.text, text.text.lower()) for i, text in enumerate(radio_labels)]
                print(f"radio options: {[opt[2] for opt in radio_options]}")  # Print lowercase versions

                if len(radio_options) == 0:
                    raise Exception("No radio options found in question")

                answer = None
                to_select = None

                # Get answer based on question type (existing logic)
                if 'driver\'s licence' in radio_text or 'driver\'s license' in radio_text:
                    answer = self.get_answer('driversLicence')
                elif any(keyword in radio_text.lower() for keyword in
                         [
                             'Aboriginal', 'native', 'indigenous', 'tribe', 'first nations',
                             'native american', 'native hawaiian', 'inuit', 'metis', 'maori',
                             'aborigine', 'ancestral', 'native peoples', 'original people',
                             'first people', 'gender', 'race', 'disability', 'latino', 'torres',
                             'do you identify'
                         ]):
                    negative_keywords = ['prefer', 'decline', 'don\'t', 'specified', 'none', 'no']
                    answer = next((option for option in radio_options if
                                   any(neg_keyword in option[2] for neg_keyword in negative_keywords)), None)

                elif 'assessment' in radio_text:
                    answer = self.get_answer("assessment")

                elif 'clearance' in radio_text:
                    answer = self.get_answer("securityClearance")

                elif 'north korea' in radio_text:
                    answer = 'no'

                elif 'previously employ' in radio_text or 'previous employ' in radio_text:
                    answer = 'no'

                elif 'authorized' in radio_text or 'authorised' in radio_text or 'legally' in radio_text:
                    answer = self.get_answer('legallyAuthorized')

                elif any(keyword in radio_text.lower() for keyword in
                         ['certified', 'certificate', 'cpa', 'chartered accountant', 'qualification']):
                    answer = self.get_answer('certifiedProfessional')

                elif 'urgent' in radio_text:
                    answer = self.get_answer('urgentFill')

                elif 'commut' in radio_text or 'on-site' in radio_text or 'hybrid' in radio_text or 'onsite' in radio_text:
                    answer = self.get_answer('commute')

                elif 'remote' in radio_text:
                    answer = self.get_answer('remote')

                elif 'background check' in radio_text:
                    answer = self.get_answer('backgroundCheck')

                elif 'drug test' in radio_text:
                    answer = self.get_answer('drugTest')

                elif 'currently living' in radio_text or 'currently reside' in radio_text or 'right to live' in radio_text:
                    answer = self.get_answer('residency')

                elif 'level of education' in radio_text:
                    for degree in self.checkboxes['degreeCompleted']:
                        if degree.lower() in radio_text:
                            answer = "yes"
                            break

                elif 'experience' in radio_text:
                    if self.experience_default > 0:
                        answer = 'yes'
                    else:
                        for experience in self.experience:
                            if experience.lower() in radio_text:
                                answer = "yes"
                                break

                elif 'data retention' in radio_text:
                    answer = 'no'

                elif 'sponsor' in radio_text:
                    answer = self.get_answer('requireVisa')

                if answer is not None:
                    print(f"Choosing answer: {answer}")
                    answer_lower = answer.lower()  # Convert answer to lowercase once

                    # 1. Try exact match first (case-insensitive)
                    for i, (_, original_text, lower_text) in enumerate(radio_options):
                        if answer_lower == lower_text:
                            to_select = radio_labels[i]
                            print(f"Found exact match: {original_text}")
                            break

                    # 2. If no exact match, try partial match
                    if to_select is None:
                        for i, (_, original_text, lower_text) in enumerate(radio_options):
                            if answer_lower in lower_text:
                                to_select = radio_labels[i]
                                print(f"Found partial match: {original_text}")
                                break

                    # 3. If still no match, look for "prefer not to answer" option
                    if to_select is None:
                        decline_keywords = [
                            "don't wish to answer",
                            "prefer not",
                            "decline",
                            "prefer not to say",
                            "prefer not to answer",
                            "do not wish to answer",
                            "choose not to answer",
                            "don't want to answer",
                            "rather not say",
                            "specified",
                            "none of the above"
                        ]
                        for i, (_, original_text, lower_text) in enumerate(radio_options):
                            if any(keyword in lower_text for keyword in decline_keywords):
                                to_select = radio_labels[i]
                                print(f"Using decline option: {original_text}")
                                break

                    # 4. If still no match, use the last option as final fallback
                    if to_select is None:
                        to_select = radio_labels[-1]
                        print(f"No match found, using last option: {radio_labels[-1].text}")

                if to_select is None:
                    print("No answer determined")
                    self.record_unprepared_question("radio", radio_text)

                    # Use AI to generate response if available
                    ai_response = self.ai_generator.generate_response(
                        question_text,
                        response_type="choice",
                        options=radio_options
                    )
                    if ai_response is not None:
                        to_select = radio_labels[ai_response]
                    else:
                        to_select = radio_labels[-1]

                to_select.click()

                if radio_labels:
                    continue
            except Exception as e:
                print("An exception occurred while filling up radio field")

            # Questions check
            try:
                question_text = question.find_element(By.TAG_NAME, 'label').text.lower()
                print( question_text )  # TODO: Put logging behind debug flag

                txt_field_visible = False
                try:
                    txt_field = question.find_element(By.TAG_NAME, 'input')
                    txt_field_visible = True
                except:
                    try:
                        txt_field = question.find_element(By.TAG_NAME, 'textarea')  # TODO: Test textarea
                        txt_field_visible = True
                    except:
                        raise Exception("Could not find textarea or input tag for question")

                if 'numeric' in txt_field.get_attribute('id').lower():
                    # For decimal and integer response fields, the id contains 'numeric' while the type remains 'text'
                    text_field_type = 'numeric'
                elif 'text' in txt_field.get_attribute('type').lower():
                    text_field_type = 'text'
                else:
                    raise Exception("Could not determine input type of input field!")

                to_enter = ''
                if 'experience' in question_text or 'how many years in' in question_text:
                    no_of_years = None
                    for experience in self.experience:
                        if experience.lower() in question_text:
                            no_of_years = int(self.experience[experience])
                            break
                    if no_of_years is None:
                        self.record_unprepared_question(text_field_type, question_text)
                        no_of_years = int(self.experience_default)
                    to_enter = no_of_years

                elif 'grade point average' in question_text:
                    to_enter = self.university_gpa

                elif 'first name' in question_text:
                    to_enter = self.personal_info['First Name']

                elif 'last name' in question_text:
                    to_enter = self.personal_info['Last Name']

                elif 'name' in question_text:
                    to_enter = self.personal_info['First Name'] + " " + self.personal_info['Last Name']

                elif 'pronouns' in question_text:
                    to_enter = self.personal_info['Pronouns']

                elif 'phone' in question_text:
                    to_enter = self.personal_info['Mobile Phone Number']

                elif 'linkedin' in question_text:
                    to_enter = self.personal_info['Linkedin']

                elif 'message to hiring' in question_text or 'cover letter' in question_text:
                    to_enter = self.personal_info['MessageToManager']

                elif 'website' in question_text or 'github' in question_text or 'portfolio' in question_text:
                    to_enter = self.personal_info['Website']

                elif 'notice' in question_text or 'weeks' in question_text:
                    if text_field_type == 'numeric':
                        to_enter = int(self.notice_period)
                    else:
                        to_enter = str(self.notice_period)

                elif 'salary' in question_text or 'expectation' in question_text or 'compensation' in question_text or 'CTC' in question_text:
                    if text_field_type == 'numeric':
                        to_enter = int(self.salary_minimum)
                    else:
                        to_enter = float(self.salary_minimum)
                    self.record_unprepared_question(text_field_type, question_text)

                # Since no response can be determined, we use AI to generate a response if available, falling back to 0 or empty string if the AI response is not available
                if text_field_type == 'numeric':
                    if not isinstance(to_enter, (int, float)):
                        ai_response = self.ai_generator.generate_response(
                            question_text,
                            response_type="numeric"
                        )
                        to_enter = ai_response if ai_response is not None else 0
                elif to_enter == '':
                    ai_response = self.ai_generator.generate_response(
                        question_text,
                        response_type="text"
                    )
                    to_enter = ai_response if ai_response is not None else " ‏‏‎ "

                self.enter_text(txt_field, to_enter)
                continue
            except:
                print("An exception occurred while filling up text field")  # TODO: Put logging behind debug flag

            # Date Check
            try:
                date_picker = question.find_element(By.CLASS_NAME, 'artdeco-datepicker__input ')
                date_picker.clear()
                date_picker.send_keys(date.today().strftime("%m/%d/%y"))
                time.sleep(3)
                date_picker.send_keys(Keys.RETURN)
                time.sleep(2)
                continue
            except:
                print("An exception occurred while filling up date picker field")  # TODO: Put logging behind debug flag

            # Dropdown check
            try:
                question_text = question.find_element(By.TAG_NAME, 'label').text.lower()
                print(f"Dropdown question text: {question_text}")  # TODO: Put logging behind debug flag
                dropdown_field = question.find_element(By.TAG_NAME, 'select')

                select = Select(dropdown_field)
                options = [options.text for options in select.options]
                print(f"Dropdown options: {options}")  # TODO: Put logging behind debug flag

                if 'proficiency' in question_text:
                    proficiency = "None"
                    for language in self.languages:
                        if language.lower() in question_text:
                            proficiency = self.languages[language]
                            break
                    self.select_dropdown(dropdown_field, proficiency)

                elif 'clearance' in question_text:
                    answer = self.get_answer('securityClearance')

                    choice = ""
                    for option in options:
                        if answer == 'yes':
                            choice = option
                        else:
                            if 'no' in option.lower():
                                choice = option
                    if choice == "":
                        self.record_unprepared_question(text_field_type, question_text)
                    self.select_dropdown(dropdown_field, choice)

                elif 'assessment' in question_text:
                    answer = self.get_answer('assessment')
                    choice = ""
                    for option in options:
                        if answer == 'yes':
                            choice = option
                        else:
                            if 'no' in option.lower():
                                choice = option
                    # if choice == "":
                    #    choice = options[len(options) - 1]
                    self.select_dropdown(dropdown_field, choice)

                elif 'commut' in question_text or 'on-site' in question_text or 'hybrid' in question_text or 'onsite' in question_text:
                    answer = self.get_answer('commute')

                    choice = ""
                    for option in options:
                        if answer == 'yes':
                            choice = option
                        else:
                            if 'no' in option.lower():
                                choice = option
                    # if choice == "":
                    #    choice = options[len(options) - 1]
                    self.select_dropdown(dropdown_field, choice)

                elif 'country code' in question_text:
                    self.select_dropdown(dropdown_field, self.personal_info['Phone Country Code'])

                elif 'north korea' in question_text:
                    choice = ""
                    for option in options:
                        if 'no' in option.lower():
                            choice = option
                    if choice == "":
                        choice = options[len(options) - 1]
                    self.select_dropdown(dropdown_field, choice)

                elif 'previously employed' in question_text or 'previous employment' in question_text:
                    choice = ""
                    for option in options:
                        if 'no' in option.lower():
                            choice = option
                    if choice == "":
                        choice = options[len(options) - 1]
                    self.select_dropdown(dropdown_field, choice)

                elif 'sponsor' in question_text:
                    answer = self.get_answer('requireVisa')
                    choice = ""
                    for option in options:
                        if answer == 'yes':
                            choice = option
                        else:
                            if 'no' in option.lower():
                                choice = option
                    if choice == "":
                        choice = options[len(options) - 1]
                    self.select_dropdown(dropdown_field, choice)

                elif 'above 18' in question_text.lower():  # Check for "above 18" in the question text
                    choice = ""
                    for option in options:
                        if 'yes' in option.lower():  # Select 'yes' option
                            choice = option
                    if choice == "":
                        choice = options[0]  # Default to the first option if 'yes' is not found
                    self.select_dropdown(dropdown_field, choice)

                elif 'currently living' in question_text or 'currently reside' in question_text:
                    answer = self.get_answer('residency')
                    choice = ""
                    for option in options:
                        if answer == 'yes':
                            choice = option
                        else:
                            if 'no' in option.lower():
                                choice = option
                    if choice == "":
                        choice = options[len(options) - 1]
                    self.select_dropdown(dropdown_field, choice)

                elif 'authorized' in question_text or 'authorised' in question_text:
                    answer = self.get_answer('legallyAuthorized')
                    choice = ""
                    for option in options:
                        if answer == 'yes':
                            # find some common words
                            choice = option
                        else:
                            if 'no' in option.lower():
                                choice = option
                    if choice == "":
                        choice = options[len(options) - 1]
                    self.select_dropdown(dropdown_field, choice)

                elif 'citizenship' in question_text:
                    answer = self.get_answer('legallyAuthorized')
                    choice = ""
                    for option in options:
                        if answer == 'yes':
                            if 'no' in option.lower():
                                choice = option
                    if choice == "":
                        choice = options[len(options) - 1]
                    self.select_dropdown(dropdown_field, choice)

                elif 'clearance' in question_text:
                    answer = self.get_answer('clearance')
                    choice = ""
                    for option in options:
                        if answer == 'yes':
                            choice = option
                        else:
                            if 'no' in option.lower():
                                choice = option
                    if choice == "":
                        choice = options[len(options) - 1]

                    self.select_dropdown(dropdown_field, choice)

                elif any(keyword in question_text.lower() for keyword in
                         [
                             'aboriginal', 'native', 'indigenous', 'tribe', 'first nations',
                             'native american', 'native hawaiian', 'inuit', 'metis', 'maori',
                             'aborigine', 'ancestral', 'native peoples', 'original people',
                             'first people', 'gender', 'race', 'disability', 'latino'
                         ]):
                    negative_keywords = ['prefer', 'decline', 'don\'t', 'specified', 'none']

                    choice = ""
                    choice = next((option for options in option.lower() if
                               any(neg_keyword in option.lower() for neg_keyword in negative_keywords)), None)

                    self.select_dropdown(dropdown_field, choice)

                elif 'email' in question_text:
                    continue  # assume email address is filled in properly by default

                elif 'experience' in question_text or 'understanding' in question_text or 'familiar' in question_text or 'comfortable' in question_text or 'able to' in question_text:
                    answer = 'no'
                    if self.experience_default > 0:
                        answer = 'yes'
                    else:
                        for experience in self.experience:
                            if experience.lower() in question_text and self.experience[experience] > 0:
                                answer = 'yes'
                                break
                    if answer == 'no':
                        # record unlisted experience as unprepared questions
                        self.record_unprepared_question("dropdown", question_text)

                    choice = ""
                    for option in options:
                        if answer in option.lower():
                            choice = option
                    if choice == "":
                        choice = options[len(options) - 1]
                    self.select_dropdown(dropdown_field, choice)

                else:
                    print(f"Unhandled dropdown question: {question_text}")
                    self.record_unprepared_question("dropdown", question_text)

                    # Since no response can be determined, we use AI to identify the best responseif available, falling back "yes" or the final response if the AI response is not available
                    choice = options[len(options) - 1]
                    choices = [(i, option) for i, option in enumerate(options)]
                    ai_response = self.ai_generator.generate_response(
                        question_text,
                        response_type="choice",
                        options=choices
                    )
                    if ai_response is not None:
                        choice = options[ai_response]
                    else:
                        choice = ""
                        for option in options:
                            if 'yes' in option.lower():
                                choice = option

                    print(f"Selected option: {choice}")
                    self.select_dropdown(dropdown_field, choice)
                continue
            except:
                print("An exception occurred while filling up dropdown field")  # TODO: Put logging behind debug flag

            # Checkbox check for agreeing to terms and service
            try:
                clickable_checkbox = question.find_element(By.TAG_NAME, 'label')
                clickable_checkbox.click()
            except:
                print("An exception occurred while filling up checkbox field")  # TODO: Put logging behind debug flag

    def unfollow(self):
        try:
            follow_checkbox = self.browser.find_element(By.XPATH,
                                                        "//label[contains(.,\'to stay up to date with their page.\')]").click()
            follow_checkbox.click()
        except:
            pass

    def send_resume(self):
        print("Trying to send resume")
        try:
            file_upload_elements = (By.CSS_SELECTOR, "input[name='file']")
            if len(self.browser.find_elements(file_upload_elements[0], file_upload_elements[1])) > 0:
                input_buttons = self.browser.find_elements(file_upload_elements[0], file_upload_elements[1])
                if len(input_buttons) == 0:
                    raise Exception("No input elements found in element")
                for upload_button in input_buttons:
                    upload_type = upload_button.find_element(By.XPATH, "..").find_element(By.XPATH,
                                                                                          "preceding-sibling::*")
                    if 'resume' in upload_type.text.lower():
                        upload_button.send_keys(self.resume_dir)
                    elif 'cover' in upload_type.text.lower():
                        if self.cover_letter_dir != '':
                            upload_button.send_keys(self.cover_letter_dir)
                        elif 'required' in upload_type.text.lower():
                            upload_button.send_keys(self.resume_dir)
        except:
            print("Failed to upload resume or cover letter!")
            pass

    def enter_text(self, element, text):
        element.clear()
        element.send_keys(text)

    def select_dropdown(self, element, text):
        select = Select(element)
        select.select_by_visible_text(text)

    # Radio Select
    def radio_select(self, element, label_text, clickLast=False):
        label = element.find_element(By.TAG_NAME, 'label')
        if label_text in label.text.lower() or clickLast == True:
            label.click()

    # Contact info fill-up
    def contact_info(self, form):
        print("Trying to fill up contact info fields")
        frm_el = form.find_elements(By.TAG_NAME, 'label')
        if len(frm_el) > 0:
            for el in frm_el:
                text = el.text.lower()
                if 'email address' in text:
                    continue
                elif 'phone number' in text:
                    try:
                        country_code_picker = el.find_element(By.XPATH,
                                                              '//select[contains(@id,"phoneNumber")][contains(@id,"country")]')
                        self.select_dropdown(country_code_picker, self.personal_info['Phone Country Code'])
                    except Exception as e:
                        print("Country code " + self.personal_info[
                            'Phone Country Code'] + " not found. Please make sure it is same as in LinkedIn.")
                        print(e)
                    try:
                        phone_number_field = el.find_element(By.XPATH,
                                                             '//input[contains(@id,"phoneNumber")][contains(@id,"nationalNumber")]')
                        self.enter_text(phone_number_field, self.personal_info['Mobile Phone Number'])
                    except Exception as e:
                        print("Could not enter phone number:")
                        print(e)

    def fill_up(self):
        try:
            easy_apply_modal_content = self.browser.find_element(By.CLASS_NAME, "jobs-easy-apply-modal__content")
            form = easy_apply_modal_content.find_element(By.TAG_NAME, 'form')
            try:
                label = form.find_element(By.TAG_NAME, 'h3').text.lower()
                if 'home address' in label:
                    self.home_address(form)
                elif 'contact info' in label:
                    self.contact_info(form)
                elif 'resume' in label:
                    self.send_resume()
                else:
                    self.additional_questions(form)
            except Exception as e:
                print("An exception occurred while filling up the form:")
                print(e)
        except:
            print("An exception occurred while searching for form in modal")

    def write_to_file(self, company, job_title, link, location, search_location):
        to_write = [company, job_title, link, location, search_location, datetime.now()]
        file_path = self.file_name + ".csv"
        print(f'updated {file_path}.')

        with open(file_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(to_write)

    def record_unprepared_question(self, answer_type, question_text):
        to_write = [answer_type, question_text]
        file_path = self.unprepared_questions_file_name + ".csv"

        try:
            with open(file_path, 'a') as f:
                writer = csv.writer(f)
                writer.writerow(to_write)
                print(f'Updated {file_path} with {to_write}.')
        except:
            print(
                "Special characters in questions are not allowed. Failed to update unprepared questions log.")
            print(question_text)

    def scroll_slow(self, scrollable_element, start=0, end=3600, step=100, reverse=False):
        if reverse:
            start, end = end, start
            step = -step

        for i in range(start, end, step):
            self.browser.execute_script("arguments[0].scrollTo(0, {})".format(i), scrollable_element)
            time.sleep(random.uniform(0.1, .6))

    def avoid_lock(self):
        if self.disable_lock:
            return

        pyautogui.keyDown('ctrl')
        pyautogui.press('esc')
        pyautogui.keyUp('ctrl')
        time.sleep(1.0)
        pyautogui.press('esc')

    def get_base_search_url(self, parameters):
        remote_url = ""
        lessthanTenApplicants_url = ""
        newestPostingsFirst_url = ""

        if parameters.get('remote'):
            remote_url = "&f_WT=2"
        else:
            remote_url = ""
            # TO DO: Others &f_WT= options { WT=1 onsite, WT=2 remote, WT=3 hybrid, f_WT=1%2C2%2C3 }

        if parameters['lessthanTenApplicants']:
            lessthanTenApplicants_url = "&f_EA=true"

        if parameters['newestPostingsFirst']:
            newestPostingsFirst_url += "&sortBy=DD"

        level = 1
        experience_level = parameters.get('experienceLevel', [])
        experience_url = "f_E="
        for key in experience_level.keys():
            if experience_level[key]:
                experience_url += "%2C" + str(level)
            level += 1

        distance_url = "?distance=" + str(parameters['distance'])

        # Get job type from parameters, default to full-time if not specified
        job_type = parameters.get('jobType', 'F')  # F = Full-time, P = Part-time, C = Contract, T = Temporary, I = Internship
        job_types_url = f"f_JT={job_type}"

        # Add salary filter using LinkedIn's salary range codes for minimum salary
        # LinkedIn salary range codes for minimum salary (f_SB2):
        # 1: $40,000+
        # 2: $60,000+
        # 3: $80,000+
        # 4: $100,000+
        # 5: $120,000+
        # 6: $140,000+
        # 7: $160,000+
        # 8: $180,000+
        # 9: $200,000+
        salary_minimum = parameters.get('salaryMinimum', 0)
        if salary_minimum >= 200000:
            salary_code = 9
        elif salary_minimum >= 180000:
            salary_code = 8
        elif salary_minimum >= 160000:
            salary_code = 7
        elif salary_minimum >= 140000:
            salary_code = 6
        elif salary_minimum >= 120000:
            salary_code = 5
        elif salary_minimum >= 100000:
            salary_code = 4
        elif salary_minimum >= 80000:
            salary_code = 3
        elif salary_minimum >= 60000:
            salary_code = 2
        elif salary_minimum >= 40000:
            salary_code = 1
        else:
            salary_code = 0  # No minimum salary filter
        salary_url = f"&f_SB2={salary_code}" if salary_code > 0 else ""

        date_url = ""
        dates = {"all time": "", "month": "&f_TPR=r2592000", "week": "&f_TPR=r604800", "24 hours": "&f_TPR=r86400"}
        date_table = parameters.get('date', [])
        for key in date_table.keys():
            if date_table[key]:
                date_url = dates[key]
                break

        easy_apply_url = "&f_AL=true"

        extra_search_terms = [distance_url, remote_url, lessthanTenApplicants_url, newestPostingsFirst_url, job_types_url, salary_url, experience_url]
        extra_search_terms_str = '&'.join(
            term for term in extra_search_terms if len(term) > 0) + easy_apply_url + date_url

        return extra_search_terms_str

    def next_job_page(self, position, location, job_page):
        """
        Navigate to the next page of job search results on LinkedIn.

        This method constructs the URL for the job search page based on the search parameters
        and navigates to that page. It optionally wraps the position in quotes for a strict search match
        based on the strictSearch parameter and appends the page number to the URL to paginate through results.

        Args:
            position (str): The job position/title to search for
            location (str): The location to search in
            job_page (int): The page number to navigate to (0-indexed)

        Returns:
            None
        """
        # Wrap position in quotes only if strict search is enabled
        search_position = f'"{position}"' if self.strict_search else position
        self.browser.get("https://www.linkedin.com/jobs/search/" + self.base_search_url +
                         "&keywords=" + search_position + location + "&start=" + str(job_page * 25))

        self.avoid_lock()

    def _format_response(self, response):
        """Format the response based on strict mode setting."""
        if not response:
            return response

        if isinstance(response, (int, float)):
            return response

        if self.strict_mode and isinstance(response, str):
            # Add quotes if they're not already present
            if not (response.startswith('"') and response.endswith('"')):
                return f'"{response}"'

        return response

    def generate_response(self, question_text, response_type="text", options=None):
        """
        Generate a response to an application question, either using AI or predefined responses.

        Args:
            question_text: The application question to answer
            response_type: "text", "numeric", or "choice"
            options: For "choice" type, a list of tuples containing (index, text) of possible answers

        Returns:
            - For text: Generated text response or predefined response
            - For numeric: Integer value
            - For choice: Integer index of selected option
        """
        if self.use_llm and self.ai_generator:
            response = self.ai_generator.generate_response(question_text, response_type, options)
            if response is not None:
                return self._format_response(response)

        # Fallback to predefined responses if LLM is disabled or failed
        if response_type == "text":
            response = self._get_predefined_text_response(question_text)
            return self._format_response(response)
        elif response_type == "numeric":
            return self._get_predefined_numeric_response(question_text)
        elif response_type == "choice" and options:
            return self._get_predefined_choice_response(question_text, options)

        return None

    def _get_predefined_text_response(self, question_text):
        """Get a predefined text response based on the question."""
        # Common questions and their predefined responses
        predefined_responses = {
            "why do you want to work here": "I am excited about the opportunity to contribute my skills and experience to your team. The role aligns well with my career goals and I believe I can make valuable contributions to your organization.",
            "what are your salary expectations": "I am flexible with salary and would be happy to discuss compensation based on the role's responsibilities and market rates.",
            "tell me about yourself": "I am a professional with experience in software development and a passion for creating efficient solutions. I enjoy tackling complex problems and working in collaborative environments.",
            "what are your strengths": "My key strengths include problem-solving abilities, attention to detail, and strong communication skills. I am also adaptable and quick to learn new technologies.",
            "what are your weaknesses": "I am continuously working on improving my time management skills and learning to delegate tasks more effectively.",
        }

        # Check for partial matches in the question
        question_lower = question_text.lower()
        for key, response in predefined_responses.items():
            if key in question_lower:
                return response

        # Default response if no match found
        return "Thank you for your question. I would be happy to discuss this further during an interview."

    def _get_predefined_numeric_response(self, question_text):
        """Get a predefined numeric response based on the question."""
        # Common numeric questions and their predefined responses
        predefined_numeric = {
            "years of experience": 3,
            "expected salary": 80000,
            "notice period": 2,
            "gpa": 3.5,
        }

        # Check for partial matches in the question
        question_lower = question_text.lower()
        for key, value in predefined_numeric.items():
            if key in question_lower:
                return value

        # Default response if no match found
        return 0

    def _get_predefined_choice_response(self, question_text, options):
        """Get a predefined choice response based on the question and available options."""
        # For choice questions, default to the first option if no specific logic is implemented
        if options and len(options) > 0:
            return 0
        return None

    def evaluate_job_fit(self, job_title, job_description):
        """
        Evaluate whether a job is worth applying to based on the candidate's experience and the job requirements.

        Args:
            job_title: The title of the job posting
            job_description: The full job description text

        Returns:
            bool: True if should apply, False if should skip
        """
        if self.use_llm and self.ai_generator:
            return self.ai_generator.evaluate_job_fit(job_title, job_description)

        # Fallback to basic evaluation if LLM is disabled
        # Check for blacklisted companies and titles
        if any(company.lower() in job_title.lower() for company in self.company_blacklist):
            return False
        if any(title.lower() in job_title.lower() for title in self.title_blacklist):
            return False

        # Default to applying if no specific reason to skip
        return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='LinkedIn Easy Apply Bot')
    parser.add_argument('--strict-position', action='store_true',
                      help='Use strict position search (exact matches only)')
    args = parser.parse_args()

    try:
        with open('config.json') as config_file:
            parameters = json.load(config_file)
    except FileNotFoundError:
        print("Config file not found. Please create a config.json file.")
        sys.exit(1)
    except json.JSONDecodeError:
        print("Config file is not valid JSON. Please check the format.")
        sys.exit(1)

    if parameters is None:
        print("Config file is empty. Please check the file.")
        sys.exit(1)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument("--remote-debugging-port=9222")

    if parameters.get('headless'):
        chrome_options.add_argument('--headless')

    driver = webdriver.Chrome(options=chrome_options)
    driver.maximize_window()

    bot = LinkedinEasyApply(parameters, driver)
    bot.login()
    bot.start_applying()

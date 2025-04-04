import yaml, os, argparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from validate_email import validate_email
from webdriver_manager.chrome import ChromeDriverManager
from linkedineasyapply import LinkedinEasyApply

def init_browser():
    browser_options = Options()
    options = [
        '--disable-blink-features',
        '--no-sandbox',
        '--start-maximized',
        '--disable-extensions',
        '--ignore-certificate-errors',
        '--disable-blink-features=AutomationControlled',
        '--remote-debugging-port=9222'
    ]

    # Restore session if possible (avoids login everytime)
    user_data_dir = os.path.join(os.getcwd(), "chrome_bot")
    browser_options.add_argument(f"user-data-dir={user_data_dir}")

    for option in options:
        browser_options.add_argument(option)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=browser_options)
    driver.implicitly_wait(1)  # Wait time in seconds to allow loading of elements
    driver.set_window_position(0, 0)
    driver.maximize_window()
    return driver

def validate_yaml(config_file="config.yaml"):
    with open(config_file, 'r', encoding='utf-8') as stream:
        try:
            parameters = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise exc

    mandatory_params = ['email',
                        'password',
                        'disableAntiLock',
                        'remote',
                        'lessthanTenApplicants',
                        'newestPostingsFirst',
                        'experienceLevel',
                        'jobTypes',
                        'date',
                        'positions',
                        'locations',
                        'residentStatus',
                        'distance',
                        'outputFileDirectory',
                        'checkboxes',
                        'universityGpa',
                        'languages',
                        'experience',
                        'personalInfo',
                        'eeo',
                        'uploads']

    for mandatory_param in mandatory_params:
        if mandatory_param not in parameters:
            raise Exception(mandatory_param + ' is not defined in the config.yaml file!')

    assert validate_email(parameters['email'])
    assert len(str(parameters['password'])) > 0
    assert isinstance(parameters['disableAntiLock'], bool)
    assert isinstance(parameters['remote'], bool)
    assert isinstance(parameters['lessthanTenApplicants'], bool)
    assert isinstance(parameters['newestPostingsFirst'], bool)
    assert isinstance(parameters['residentStatus'], bool)
    assert len(parameters['experienceLevel']) > 0
    experience_level = parameters.get('experienceLevel', [])
    at_least_one_experience = False

    for key in experience_level.keys():
        if experience_level[key]:
            at_least_one_experience = True
    assert at_least_one_experience

    assert len(parameters['jobTypes']) > 0
    job_types = parameters.get('jobTypes', [])
    at_least_one_job_type = False
    for key in job_types.keys():
        if job_types[key]:
            at_least_one_job_type = True

    assert at_least_one_job_type
    assert len(parameters['date']) > 0
    date = parameters.get('date', [])
    at_least_one_date = False

    for key in date.keys():
        if date[key]:
            at_least_one_date = True
    assert at_least_one_date

    approved_distances = {0, 5, 10, 25, 50, 100}
    assert parameters['distance'] in approved_distances
    assert len(parameters['positions']) > 0
    assert len(parameters['locations']) > 0
    assert len(parameters['uploads']) >= 1 and 'resume' in parameters['uploads']
    assert len(parameters['checkboxes']) > 0

    checkboxes = parameters.get('checkboxes', [])
    assert isinstance(checkboxes['driversLicence'], bool)
    assert isinstance(checkboxes['requireVisa'], bool)
    assert isinstance(checkboxes['legallyAuthorized'], bool)
    assert isinstance(checkboxes['certifiedProfessional'], bool)
    assert isinstance(checkboxes['urgentFill'], bool)
    assert isinstance(checkboxes['commute'], bool)
    assert isinstance(checkboxes['backgroundCheck'], bool)
    assert isinstance(checkboxes['securityClearance'], bool)
    assert 'degreeCompleted' in checkboxes
    assert isinstance(parameters['universityGpa'], (int, float))

    languages = parameters.get('languages', [])
    language_types = {'none', 'conversational', 'professional', 'native or bilingual'}
    # for language in languages:
    #     assert languages[language].lower() in language_types

    experience = parameters.get('experience', [])
    for tech in experience:
        assert isinstance(experience[tech], int)
    assert 'default' in experience

    assert len(parameters['personalInfo'])
    personal_info = parameters.get('personalInfo', [])
    for info in personal_info:
        assert personal_info[info] != ''

    assert len(parameters['eeo'])
    eeo = parameters.get('eeo', [])
    for survey_question in eeo:
        assert eeo[survey_question] != ''

    if parameters.get('openaiApiKey') == '':
        # Overwrite the default value with None to indicate internally that the OpenAI API key is not configured
        parameters['openaiApiKey'] = None

    return parameters

def parse_arguments():
    parser = argparse.ArgumentParser(description='AIEasyApply - LinkedIn Job Application Bot')
    parser.add_argument('--no-llm', action='store_true', help='Run without using LLM/AI for responses')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode with verbose output')
    parser.add_argument('--config', type=str, default='config.yaml', help='Path to custom configuration file')
    parser.add_argument('--strict-title', action='store_true', help='Use strict job title search (exact matches only)')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_arguments()

    # Load and validate configuration
    parameters = validate_yaml(args.config)

    # Set debug mode if specified
    if args.debug:
        parameters['debug'] = True
        print("Running in debug mode with verbose output")

    # Disable LLM if specified
    if args.no_llm:
        print("Running without LLM/AI - using predefined responses only")
        parameters['useLLM'] = False
    else:
        parameters['useLLM'] = True

    # Set strict title search if specified
    if args.strict_title:
        print("Using strict job title search - exact matches only")
        parameters['strictSearch'] = True
    else:
        parameters['strictSearch'] = False

    # Initialize browser and start the bot
    browser = init_browser()
    bot = LinkedinEasyApply(parameters, browser)
    bot.login()
    bot.security_check()
    bot.start_applying()

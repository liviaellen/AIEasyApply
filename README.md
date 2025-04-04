# AIEasyApply

A Python-based LinkedIn job application bot that automates the job application process using Selenium and OpenAI's GPT-3.5.

## ⚠️ Important Note

This tool is provided for educational purposes only. Automated job applications may violate LinkedIn's terms of service. Use at your own risk.

## 🔒 Account Setup

**Important:** For security reasons, we strongly recommend creating a dedicated LinkedIn account for this bot. This helps:

- Protect your main professional account from potential restrictions
- Isolate bot activity from your personal networking
- Prevent accidental applications to positions you're not interested in
- Maintain a clean separation between automated and manual job applications

To create a new account:
1. Use a different email address than your main LinkedIn account
2. Complete the basic profile information
3. Add minimal professional details to avoid triggering LinkedIn's security measures
4. Use this account exclusively for the bot

## 🎯 Initial Setup Tips

**Important:** Before running the bot, we strongly recommend:

1. **Manual Applications First**:
   - Apply to 3-5 jobs manually on LinkedIn
   - Make sure to apply to jobs that require resume upload
   - This ensures your LinkedIn profile has basic information saved
   - Helps the bot handle future applications more effectively
   - Creates a baseline for LinkedIn's application format

The manual applications help because:
- LinkedIn saves your basic information from these applications
- It creates a history of normal application behavior
- Provides fallback responses if the bot encounters issues
- Reduces the risk of account flags for unusual activity

## 🛠️ Installation

1. Clone this repository
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure your settings in `config.yaml`

## 🏃‍♂️ Usage

Run the bot with:

```bash
python main.py
```

### Command-line Options

The bot supports several command-line arguments:

```bash
# Run with default settings (using AI for responses)
python main.py

# Run without AI/LLM (using predefined responses only)
python main.py --no-llm

# Run with strict job title search (exact matches only)
python main.py --strict-title

# Run in debug mode with verbose output
python main.py --debug

# Run with a specific configuration file
python main.py --config custom_config.yaml
```

#### Command Arguments

- `--no-llm`: Use predefined responses instead of AI-generated ones
- `--strict-title`: Enable strict job title search (wraps job titles in quotes for exact matches)
- `--debug`: Enable verbose logging for troubleshooting
- `--config`: Specify a custom configuration file path

Example job searches with and without strict title mode:

```
# Normal mode (--strict-title not used)
Job Title: Software Engineer
→ Matches: "Software Engineer", "Senior Software Engineer", "Software Engineer II", etc.

# Strict mode (--strict-title used)
Job Title: Software Engineer
→ Matches: Only exact "Software Engineer" positions
```

### Response Generation Modes

The bot can operate in two modes:

1. **AI Mode (Default)**
   - Uses OpenAI's GPT-3.5 to generate personalized responses
   - Requires an OpenAI API key in config.yaml
   - Provides more natural and context-aware answers
   - Better at handling complex or unexpected questions
   - Higher computational resource usage and carbon footprint
   - Incurs API costs for each response

2. **Predefined Mode (--no-llm)**
   - Uses a set of predefined responses for common questions
   - No API key required
   - Faster and more predictable
   - Limited to common application questions
   - Good for testing or when API access is not available
   - More environmentally friendly (no additional compute resources needed)
   - Zero operational costs

### Sustainability Considerations

When choosing between AI and predefined modes, consider:

1. **Environmental Impact**
   - AI Mode: Each response requires significant compute resources
   - Predefined Mode: Minimal environmental impact, using only basic operations

2. **Resource Efficiency**
   - AI Mode: Higher latency, API costs, and resource usage
   - Predefined Mode: Instant responses, no external dependencies

3. **Cost Effectiveness**
   - AI Mode: Costs scale with usage (OpenAI API charges)
   - Predefined Mode: Free to use, no ongoing costs

Choose the mode that best aligns with your sustainability goals and practical needs.

The bot will:
1. Log into your LinkedIn account
2. Search for jobs based on your criteria
3. Apply to matching positions using the Easy Apply feature
4. Generate responses to application questions (AI-powered or predefined)
5. Track all applications in a CSV file

## 📋 Configuration

Edit the `config.yaml` file to customize:
- LinkedIn credentials
- Job search criteria
- Application preferences
- OpenAI API key (optional, only needed for AI mode)
- Personal information for applications
- Resume and cover letter paths

## ⚙️ Features

- Automated job search and application
- Smart response generation (AI or predefined)
- Job fit evaluation
- Application tracking
- Session persistence
- Anti-detection measures
- Debug mode for troubleshooting

## 📝 Notes

- The bot includes built-in delays to mimic human behavior
- It handles various types of application questions (text, numeric, multiple choice)
- Applications are tracked in a CSV file for reference
- Failed applications are logged separately for review

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📜 License

This project is licensed under the GPL-3.0 License - see the LICENSE file for details.

## 🙏 Acknowledgments

This project builds upon the work of several contributors:

- Original concept: [Nathan Duma](https://github.com/NathanDuma)
- Significant improvements: [Micheal Dingess](https://github.com/madingess/)
- Enhanced features: [voidbydefault](https://github.com/voidbydefault) with [EasyApplyBot](https://github.com/voidbydefault/EasyApplyBot)
- Current development: [liviaellen](https://github.com/liviaellen)

## 📞 Support

If you encounter any issues, please file them on the [GitHub issues page](https://github.com/liviaellen/AIEasyApply/issues).

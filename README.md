# ICBC Road Test Appointment Checker

An automated tool that checks for available road test appointments at the ICBC Richmond Lansdowne Centre location. The script uses Selenium for web automation and sends notifications through Discord when new appointments become available.

## Features

- Automated checking of ICBC road test appointments
- Discord notifications for:
  - New appointment availability
  - Current appointment status
  - System status updates
  - Error notifications
- Headless Chrome browser operation
- Configurable check intervals
- Detailed logging system

## Prerequisites

- Python 3.7+
- Google Chrome browser
- Discord bot token and channel
- ICBC account credentials

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/wilsonxfeng/icbc-appointment-checker.git
   cd icbc-appointment-checker
   ```

2. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root with the following content:
   ```
   # ICBC Credentials
   ICBC_LAST_NAME=your_last_name
   ICBC_LEARNER_LICENSE=your_license_number
   ICBC_KEYWORD=your_keyword

   # Discord Configuration
   DISCORD_BOT_TOKEN=your_discord_bot_token
   DISCORD_CHANNEL_ID=your_channel_id

   # Check interval (in minutes)
   CHECK_INTERVAL_MINUTES=5
   ```

## Usage

Run the script:
```bash
python icbc_checker.py
```

The script will:
1. Initialize a headless Chrome browser
2. Log into your ICBC account
3. Check for available appointments at Richmond Lansdowne Centre
4. Send notifications through Discord
5. Repeat the check based on the configured interval

## Logging

The script creates two log files:
- `icbc_checker.log`: Contains detailed application logs
- `chromedriver.log`: Contains WebDriver-specific logs

## Contributing

Feel free to fork the repository and submit pull requests for any improvements.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is for personal use only. Please ensure you comply with ICBC's terms of service when using this script. 

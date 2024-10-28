# Discord Clip Downloader Bot

This Python script creates a Discord bot that automatically processes clips from various platforms shared in your Discord server. It can download, transcode, and share these clips directly within Discord, ensuring they fit Discord's upload size limitations.

**Supported Platforms:**

* Twitch Clips
* Streamable
* Twitter (using fxtwitter.com for embedded viewing)

**Requirements:**

* Python 3.6 or later
* FFmpeg (for video processing and transcoding)
* Curl (for HTTP requests)
* Discord.py library
* Requests library (for HTTP requests)
* Decouple (for environment configuration)

**Setup:**

1. **Install Dependencies:**

   ```bash
   pip install discord.py requests python-decouple

**Environment Configuration:**

Create a file named .env in the project root directory.
Add the following variables to the .env file, replacing placeholders with your actual information:
  ````bash
  BOT_TOKEN=<Your Discord Bot Token>
  TTV_CLIENT_ID=<Your Twitch Client ID>
  TTV_CLIENT_SECRET=<Your Twitch Client Secret>
  ````

**Install FFmpeg:**

FFmpeg is required for transcoding videos. Install it using your system's package manager (e.g., brew install ffmpeg on macOS) or download it from the official website.
Running the Bot:

Start the bot by running the script:

  ````Bash
  python3 <script_name>.py
  ````

This script requires valid Twitch API credentials for accessing clip details.
This script is distributed under the MIT License.
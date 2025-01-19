#!/usr/bin/env python3
from decouple import config
import discord
import os
import subprocess
import requests
import re
import json
import asyncio
from urllib.parse import quote
# Discord token
TOKEN = config('BOT_TOKEN')
client_id = config('TTV_CLIENT_ID')
client_secret = config('TTV_CLIENT_SECRET')


def get_access_token(client_id, client_secret):
    url = "https://id.twitch.tv/oauth2/token"
    headers = {
        "User-Agent": "curl/7.64.1",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }
    response = requests.post(url, data=payload, headers=headers)
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        print("Error getting access token:", response.text)
        return None


def get_clip_info(access_token, client_id, clip_id):
    url = f"https://api.twitch.tv/helix/clips?id={clip_id}"
    headers = {
        "User-Agent": "curl/7.64.1",
        "Authorization": f"Bearer {access_token}",
        "Client-Id": client_id
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["data"][0]
    else:
        print("Error getting clip info:", response.text)
        return None


def download_clip(clip_info, filename):
    print(clip_info)
    thumbnail_url = clip_info["thumbnail_url"]
    print(thumbnail_url)
    # Use regex to remove "-preview-480x272.jpg" from thumbnail url to get the video url
    video_url = re.sub(r'(-preview-.*)', '', thumbnail_url) + ".mp4"
    response = requests.get(video_url)
    print(video_url)
    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
    else:
        print("Error downloading clip:", response.text)

def get_highest_quality_url(access_token, clip_slug):
    # Define the URL and headers
    url = "https://gql.twitch.tv/gql"
    headers = {
        "Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko",
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    # Define the body for the POST request
    body = {
        "operationName": "VideoQualities",
        "variables": {
            "clipSlug": clip_slug
        },
        "query": """
        query VideoQualities($clipSlug: ID!) {
            clip(slug: $clipSlug) {
                durationSeconds
                videoQualities {
                    quality
                    frameRate
                    sourceURL
                }
                playbackAccessToken(params: { disableHTTPS: false, hasAdblock: false, platform: "web", playerBackend: "mediaplayer", playerType: "video" }) {
                    signature
                    value
                }
            }
        }
        """
    }
    # Make the POST request
    response = requests.post(url, headers=headers, json=body)

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the JSON response
        data = response.json()
        # Extract duration, video qualities, and playback access token
        duration_seconds = data.get("data", {}).get("clip", {}).get("durationSeconds", "Unknown")
        video_qualities = data.get("data", {}).get("clip", {}).get("videoQualities", [])
        playback_access_token = data.get("data", {}).get("clip", {}).get("playbackAccessToken", {})

        if video_qualities:
            # Find the highest quality URL
            highest_quality = max(video_qualities, key=lambda x: int(x.get('quality', 0)))
            base_url = highest_quality.get("sourceURL")
            signature = playback_access_token.get("signature")
            token = playback_access_token.get("value")

            # Append signature and token to the URL
            if base_url and signature and token:
                # URL-encode the token
                encoded_token = quote(token)
                formatted_url = f"{base_url}?sig={signature}&token={encoded_token}"
                print(f"Duration: {duration_seconds} seconds")
                print(f"Highest Quality URL: {formatted_url}")
                return formatted_url
            else:
                print("Could not format the URL properly.")
                return None
        else:
            print("No video qualities found.")
            return None
    else:
        # Print the error and return None
        print(f"Error: {response.status_code} - {response.text}")
        return None


def download(clip_id):
    filename = f"clip-{clip_id}.mp4"

    access_token = get_access_token(client_id, client_secret)
    if access_token is None:
        print("Couldn't get access token")
        return
    clip_info = get_clip_info(access_token, client_id, clip_id)
    if clip_info is None:
        print("Failed to get clip info")
        return
    video_url = get_highest_quality_url(access_token,clip_id)
    response = requests.get(video_url)
    print(video_url)
    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
    else:
        print("Error downloading clip:", response.text)

    return (filename, f"{clip_info['broadcaster_name']} - {clip_info['title']}")



async def get_video_duration(file):
    proc = await asyncio.create_subprocess_exec(
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', f'{file}',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    stdout, _ = await proc.communicate()
    data = json.loads(stdout.decode())
    duration = float(data['format']['duration'])
    return duration

TARGET_SIZE_MB = 23
BITRATE_CALC_FACTOR = 8 * TARGET_SIZE_MB

# Function to get video duration using FFmpeg
async def get_video_duration(file):
    process = await asyncio.create_subprocess_exec(
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', file,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise Exception(f"Error retrieving video duration: {stderr.decode()}")

    return float(stdout.decode().strip())

# Transcoding function with dynamic file size
async def transcode(file, boost_level):
    max_size = get_max_file_size(boost_level)
    target_size_mb = max_size / (1024 * 1024)  # Convert bytes to MB
    bitrate_calc_factor = 8 * target_size_mb

    duration = await get_video_duration(file)
    bitrate = (bitrate_calc_factor / duration)  # in Mbps

    print(f"Transcoding video file at {bitrate:.2f} Mbps")
    process = await asyncio.create_subprocess_exec(
        'ffmpeg', '-y', '-i', file, '-c:v', 'libx264', '-b:v', f'{bitrate}M', f'{file}.transcode.mp4',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        print(f"An error occurred during transcoding: {stderr.decode()}")
        return None
    else:
        print("Transcoding completed successfully.")
        return f'{file}.transcode.mp4'

# Recontainerizing function with dynamic file size
async def recontainerize(file, boost_level):
    print("Recontainerizing video file")
    process = await asyncio.create_subprocess_exec(
        'ffmpeg', '-y', '-i', file, f'{file}.transcode.mp4', '-codec', 'copy',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        print(f"An error occurred during recontainerizing: {stderr.decode()}")
        return None
    else:
        print("Recontainerizing completed successfully.")
        return f'{file}.transcode.mp4'

def download_streamable(slug):
    url = f"https://api.streamable.com/videos/{slug}"
    response = requests.get(url)
    if response.status_code == 200:
        file_url = response.json()["files"]["mp4"]["url"]
        title = response.json()["title"]

        response = requests.get(file_url)
        if response.status_code == 200:
            with open(f"{slug}.mp4", "wb") as f:
                f.write(response.content)
                return (f"{slug}.mp4", title)
    else:
        print("Error getting clip info:", response.text)
        return (None, None)

def get_max_file_size(boost_level):
    size_limits = {
        0: 8 * 1024 * 1024,
        1: 8 * 1024 * 1024,
        2: 50 * 1024 * 1024,
        3: 100 * 1024 * 1024,
    }
    return size_limits.get(boost_level, 8 * 1024 * 1024)

class MyClient(discord.Client):
    mobius_counter = 0

    async def on_ready(self):
        for guild in self.guilds:
            print(f'Connected to: {guild.name}')

    async def on_message(self, message):
        if message.author == client.user:
            return

        # regex pattern for URLs
        pattern = r"https://clips.twitch.tv/[A-Za-z0-9_-]*"

        done_slugs = []

        original_embeds = message.embeds

        should_remove_embeds = False

       # Find all matches
        matches = re.findall(pattern, message.content)
        for match in matches:
            print(f"Message from {message.author.name}")

            full_url = match  # entire URL
            slug = full_url.split('/')[-1]  # slug is the last part of the URL after the last slash

            if slug in done_slugs:
                continue

            async with message.channel.typing():
                done_slugs.append(slug)

                print(f"Found a Twitch clip link: {full_url}, Slug: {slug}")

                file, title = download(slug)  # Ensure download is properly defined in your context
                file_size = os.path.getsize(file)

                # Check if title contains URLs and wrap them in <>
                url_pattern = r"(https?://[^\s]+)"
                title = re.sub(url_pattern, r'<\1>', title)

                print(f"\ttitle: {title}")

                guild = message.guild

                if not guild:
                    await message.channel.send("This command must be used in a server.")
                    return
                boost_level = guild.premium_tier
                max_size = get_max_file_size(boost_level)

                if file_size > max_size:
                    await message.channel.send("Video is too large to send, attempting to shrink it - this might take a moment. Please wait.")
                    print("Transcoding Twitch video file")
                    await transcode(file)  # Ensure transcode is properly defined in your context

                    await message.channel.send(content=title, file=discord.File(f'{file}.transcode.mp4'))

                    # os.remove(f'{file}.transcode.mp4')
                else:
                    print("Sending Twitch clip file to Discord")
                    await message.channel.send(content=title, file=discord.File(f'{file}'))

                should_remove_embeds = True
                if should_remove_embeds:
                    await message.edit(suppress=True)
                os.remove(file)

        # Updated regex pattern to exclude specific Twitch clips URL
        pattern = r"https:\/\/(?:www\.twitch\.tv\/[A-Za-z0-9_-]+\/clip\/|clips\.twitch\.tv\/)[A-Za-z0-9_-]+"

        done_slugs = []

        original_embeds = message.embeds

        should_remove_embeds = False

        # Find all matches
        matches = re.findall(pattern, message.content)
        for match in matches:
            print(f"Message from {message.author.name}")

            full_url = match  # entire URL
            full_url = full_url.replace("clip/","")
            print(full_url)
            # Skip if the URL matches the specific pattern to be excluded
            if re.match(r"https://clips.twitch.tv/[A-Za-z0-9_-]*", full_url):
                print(f"Skipping URL: {full_url}")
                continue

            slug = full_url.split('/')[-1]  # For other URLs, take the last segment

            if slug in done_slugs:
                continue

            async with message.channel.typing():
                done_slugs.append(slug)

                print(f"Found a Twitch clip link 305: {full_url}, Slug: {slug}")

                file, title = download(slug)  # Ensure download is properly defined in your context
                file_size = os.path.getsize(file)

                # Check if title contains URLs and wrap them in <>
                url_pattern = r"(https?://[^\s]+)"
                title = re.sub(url_pattern, r'<\1>', title)

                print(f"\ttitle: {title}")

                guild = message.guild

                if not guild:
                    await message.channel.send("This command must be used in a server.")
                    return
                boost_level = guild.premium_tier
                max_size = get_max_file_size(boost_level)

                if file_size > max_size:
                    await message.channel.send("Video is too large to send, attempting to shrink it - this might take a moment. Please wait.")
                    print("Transcoding Twitch video file")
                    await transcode(file)  # Ensure transcode is properly defined in your context

                    await message.channel.send(content=title, file=discord.File(f'{file}.transcode.mp4'))

                    # os.remove(f'{file}.transcode.mp4')
                else:
                    print("Sending Twitch clip file to Discord")
                    await message.channel.send(content=title, file=discord.File(f'{file}'))

                should_remove_embeds = True

                os.remove(file)

        pattern = r"https://streamable.com/[A-Za-z0-9_-]*"

        done_slugs = []

        matches = re.findall(pattern, message.content)
        for match in matches:
            print(f"Message from {message.author.name}")

            full_url = match  # entire URL
            slug = full_url.split('/')[-1]  # slug is the last part of the URL after the last slash

            if slug in done_slugs:
                continue

            async with message.channel.typing():
                done_slugs.append(slug)

                print(f"Found a Streamable clip link: {full_url}, Slug: {slug}")

                file, title = download_streamable(slug)
                file_size = os.path.getsize(file)

                # title = ""
                # for embed in message.embeds:
                #     if slug in embed.url:
                #         title = embed.title

                print(f"\ttitle: {title}")

                if (file_size > 24 * 1024 * 1024):
                    print("Transcoding Streamable video file")
                    await transcode(file)
                    await message.channel.send(content=title, file=discord.File(f'{file}.transcode.mp4'))

                    os.remove(f'{file}.transcode.mp4')
                else:
                    print("Sending Streamable clip file to Discord")
                    await message.channel.send(content=title, file=discord.File(f'{file}'))

                should_remove_embeds = True

                os.remove(file)

        # Pattern for Instagram URLs
        pattern_instagram = r"https://(?:www\.)?instagram\.com/p/[A-Za-z0-9_\-]+/\?igsh=[A-Za-z0-9_\-]+"

        done_slugs = []

        matches = re.findall(pattern_instagram, message.content)
        for match in matches:
            print(f"Message from {message.author.name}")

            full_url = match  # entire URL
            full_url = full_url.replace("instagram.com", "ddinstagram.com")  # Transform to ddinstagram.com

            slug = full_url.split('/')[-1]  # Extract the slug (last part of the URL)

            if slug in done_slugs:
                continue

            async with message.channel.typing():
                done_slugs.append(slug)

                print(f"Found an Instagram post link: {full_url}, Slug: {slug}")
                await message.channel.send(full_url)

                should_remove_embeds = True


        pattern_twitter = r"https://(?:www\.)?twitter\.com/[A-Za-z0-9_]+/status/\d+"
        pattern_x = r"https://(?:www\.)?x\.com/[A-Za-z0-9_]+/status/\d+"
        combined_pattern = f"({pattern_twitter})|({pattern_x})"

        done_slugs = []

        matches = re.findall(combined_pattern, message.content)
        for match in matches:
            print(f"Message from {message.author.name}")

            for url in match:
                if url:
                    full_url = url  # entire URL
                    full_url = full_url.replace("twitter.com", "fxtwitter.com")
                    full_url = full_url.replace("x.com", "fxtwitter.com")


            #if slug in done_slugs:
            #    continue

            async with message.channel.typing():
                #done_slugs.append(slug)

                #print(f"Found a twitter tweet link: {full_url}, Slug: {slug}")
                print("Sending twitter tweet to Discord")
                await message.channel.send(full_url)

                should_remove_embeds = True



        if should_remove_embeds:
            await message.edit(suppress=True)

        attachments = message.attachments
        for attachment in attachments:
            if attachment.filename.endswith(".mkv"):
                print(f"Message from {message.author.name}")

                async with message.channel.typing():
                    await attachment.save(attachment.filename)

                    if (attachment.size > 24 * 1024 * 1024):
                        print("Transcoding large video file")
                        await transcode(attachment.filename)
                    else:
                        print("Re-containering video file")
                        await recontainerize(attachment.filename)

                    await message.channel.send(file=discord.File(f'{attachment.filename}.transcode.mp4'))

                    print("Sent file")

                    os.remove(f'{attachment.filename}')
                    os.remove(f'{attachment.filename}.transcode.mp4')


intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

client = MyClient(intents=intents)
client.run(TOKEN)


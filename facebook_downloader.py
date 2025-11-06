#!/usr/bin/env python3

# facebook_downloader.py

# Usage:

#   python facebook_downloader.py "https://www.facebook.com/.../videos/..."



from yt_dlp import YoutubeDL

from pathlib import Path

import sys



def progress_hook(d):

    if d['status'] == 'downloading':

        total = d.get('total_bytes') or d.get('total_bytes_estimate')

        downloaded = d.get('downloaded_bytes', 0)

        if total:

            pct = downloaded / total * 100

            print(f"\rDownloading... {pct:05.2f}%", end="")

    elif d['status'] == 'finished':

        print("\n✅ Download completed!")



def download_facebook_video(url, out_dir="downloads"):

    Path(out_dir).mkdir(parents=True, exist_ok=True)



    ydl_opts = {

        'outtmpl': f'{out_dir}/%(title)s.%(ext)s',

        'format': 'best',

        'noplaylist': True,

        'progress_hooks': [progress_hook],

        'quiet': False,

        'no_warnings': True

    }



    try:

        with YoutubeDL(ydl_opts) as ydl:

            ydl.download([url])

    except Exception as e:

        print("❌ Could not download Facebook video.")

        print("Possible reasons:")

        print("• The video is private or restricted")

        print("• The link format is incorrect")

        print("• Facebook temporarily blocked the request")

        print("\n✅ Make sure:")

        print("• The video is public")

        print("• URL format: https://www.facebook.com/username/videos/VIDEO_ID")

        print("\nError details:", e)



if __name__ == "__main__":

    if len(sys.argv) < 2:

        print("Usage: python facebook_downloader.py <Facebook Video URL>")

        sys.exit(1)



    video_url = sys.argv[1]

    download_facebook_video(video_url)






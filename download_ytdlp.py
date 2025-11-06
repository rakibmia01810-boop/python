#!/usr/bin/env python3

# download_ytdlp.py

# Usage examples:

# python download_ytdlp.py "YOUTUBE_URL" --best  # best video+audio

# python download_ytdlp.py "YOUTUBE_URL" --res 720  # prefer 720p

# python download_ytdlp.py "YOUTUBE_URL" --audio  # audio only (mp3)



import argparse

from yt_dlp import YoutubeDL

from pathlib import Path



def build_opts(output_dir="downloads", pref_res=None, audio_only=False):

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    outtmpl = f"{output_dir}/%(title)s - %(id)s.%(ext)s"

    opts = {

        "outtmpl": outtmpl,

        "noplaylist": True,

        "continuedl": True,

        "quiet": False,

        "no_warnings": True,

        "progress_hooks": [progress_hook],

    }

    if audio_only:

        opts.update({

            "format": "bestaudio/best",

            "postprocessors": [{

                "key": "FFmpegExtractAudio",

                "preferredcodec": "mp3",

                "preferredquality": "192",

            }],

        })

    else:

        # If user requests preference resolution, try to get bestvideo+bestaudio with height <= pref_res

        if pref_res:

            # yt-dlp format selector: choose bestvideo with height<=pref_res + bestaudio

            opts["format"] = f"bestvideo[height<={pref_res}]+bestaudio/best[height<={pref_res}]/best"

        else:

            opts["format"] = "bestvideo+bestaudio/best"

    return opts



def progress_hook(d):

    if d['status'] == 'downloading':

        total = d.get('total_bytes') or d.get('total_bytes_estimate')

        downloaded = d.get('downloaded_bytes', 0)

        if total:

            pct = downloaded / total * 100

            print(f"\rDownloading... {pct:05.2f}% ", end="")

        else:

            print(f"\rDownloading... {downloaded} bytes", end="")

    elif d['status'] == 'finished':

        print("\nDownload finished, now post-processing...")



def download(url, pref_res=None, audio_only=False, out_dir="downloads"):

    opts = build_opts(output_dir=out_dir, pref_res=pref_res, audio_only=audio_only)

    with YoutubeDL(opts) as ydl:

        ydl.download([url])



def main():

    parser = argparse.ArgumentParser(description="Download YouTube videos using yt-dlp")

    parser.add_argument("url", help="YouTube video URL")

    parser.add_argument("--res", type=int, help="Preferred max resolution (e.g., 720)")

    parser.add_argument("--audio", action="store_true", help="Download audio only (mp3)")

    parser.add_argument("--out", default="downloads", help="Output directory")

    args = parser.parse_args()



    try:

        download(args.url, pref_res=args.res, audio_only=args.audio, out_dir=args.out)

    except Exception as e:

        print("Error:", e)



if __name__ == "__main__":

    main()







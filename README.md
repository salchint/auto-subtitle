# Automatic subtitles in your videos

This repository uses `ffmpeg` and [OpenAI's Whisper](https://openai.com/blog/whisper) to automatically generate and overlay subtitles on any video.

## Installation

To get started, you'll need Python 3.7 or newer. Install the binary by running the following command:

    pip install git+https://github.com/m1guelpf/auto-subtitle.git

You'll also need to install [`ffmpeg`](https://ffmpeg.org/), which is available from most package managers:

```bash
# on Ubuntu or Debian
sudo apt update && sudo apt install ffmpeg

# on MacOS using Homebrew (https://brew.sh/)
brew install ffmpeg

# on Windows using Chocolatey (https://chocolatey.org/)
choco install ffmpeg
```

## Usage

The following command will generate a `subtitled/video.mp4` file contained the input video with overlayed subtitles.

    auto_subtitle /path/to/video.mp4 -o subtitled/

The default setting (which selects the `small` model) works well for transcribing English. You can optionally use a bigger model for better results (especially with other languages). The available models are `tiny`, `tiny.en`, `base`, `base.en`, `small`, `small.en`, `medium`, `medium.en`, `large`.

    auto_subtitle /path/to/video.mp4 --model medium

Adding `--task translate` will translate the subtitles into English:

    auto_subtitle /path/to/video.mp4 --task translate

### Subtitle style

By default, subtitles are rendered in the `Aerolite` font in dark navy blue (`#1B2A4A`) on a slightly transparent warm gold box (`#F2C14ECC`, 80% opacity) at the bottom of the video. You can change this with:

- `--font` – name of any installed font (e.g. `"DejaVu Sans"`)
- `--font_size` – font size, relative to a 288px-high canvas and scaled to the video (default `18`)
- `--font_colour` / `--font_color` – text colour as `#RRGGBB`, or `#RRGGBBAA` where `AA` is the opacity
- `--background_colour` / `--background_color` – colour of the box behind the text, same format
- `--position` – one of `bottom`, `top`, `center`, `left`, `right`, `bottom-left`, `bottom-right`, `top-left`, `top-right`
- `--max_lines` – maximum number of lines shown at once (default `1`)
- `--max_line_width` – maximum characters per line (default `42`). Longer passages are split into several short subtitles, timed using Whisper's word timestamps. `0` keeps Whisper's original segments.
- `--animation` – word-by-word animation (default `none`):
  - `karaoke` – the whole line is visible and the word being spoken is coloured in the highlight colour
  - `pop` – each word pops in (grows, overshoots slightly and settles) at the moment it is spoken
- `--highlight_colour` / `--highlight_color` – colour of the spoken word with `--animation karaoke` (default deep crimson `#A4161A`)

Animated subtitles are rendered from an `.ass` file (saved next to the `.srt` when `--output_srt true` is used).

For example, white text on a semi-transparent black box at the top:

    auto_subtitle /path/to/video.mp4 --font "DejaVu Sans" --font_color "#FFFFFF" --background_color "#000000AA" --position top

Run the following to view all available options:

    auto_subtitle --help

## License

This script is open-source and licensed under the MIT License. For more details, check the [LICENSE](LICENSE) file.

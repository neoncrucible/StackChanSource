`stream-tone.mp3` is a generated 4-second, 440 Hz mono test tone, not recorded
speech. It exercises incremental decoding and packaged native dependencies.

Generated with:

```sh
ffmpeg -f lavfi -i 'sine=frequency=440:sample_rate=24000:duration=4' -c:a libmp3lame -b:a 48k -write_xing 0 stream-tone.mp3
```

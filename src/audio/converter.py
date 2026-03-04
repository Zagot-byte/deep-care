# ONE job: convert any audio format → wav
# Uses ffmpeg subprocess
# Input:  raw bytes (webm/ogg/mp3)
# Output: wav bytes at 16kHz mono

def convert_to_wav(audio_bytes: bytes, input_format: str = "webm") -> bytes:
    # write input to /tmp/input.{format}
    # run: ffmpeg -i input.webm -ar 16000 -ac 1 output.wav
    # read output.wav bytes
    # delete both tmp files
    # return wav bytes

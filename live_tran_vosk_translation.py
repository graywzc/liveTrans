import sounddevice as sd
import queue
import json
import threading
from vosk import Model, KaldiRecognizer
import tkinter as tk
from deep_translator import GoogleTranslator

import numpy as np  # you already have it in your other script; add if missing

SILENCE_RMS = 200       # tune this for your mic/room
SILENCE_HANG = 5        # how many consecutive silent blocks before we treat as paused

def is_near_silence(data_bytes, rms_thresh=SILENCE_RMS):
    buf = np.frombuffer(data_bytes, dtype=np.int16)
    if buf.size == 0:
        return True, 0.0
    # float32 to avoid int16 overflow in squaring
    rms = float(np.sqrt(np.mean(buf.astype(np.float32) ** 2)))
    return (rms < rms_thresh), rms

# === CONFIG ===
MODEL_PATH = "model-ja"
SAMPLE_RATE = 16000

model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, SAMPLE_RATE)
audio_queue = queue.Queue()

# Holds final transcript + translation
full_transcript = ""


from pykakasi import Kakasi

def add_furigana(text):
    kakasi = Kakasi()
    result = ""

    for item in kakasi.convert(text):
        orig = item["orig"]
        hira = item["hira"]
        if orig != hira:
            result += f"{orig}({hira})"
        else:
            result += orig
    return result




def audio_callback(indata, frames, time, status):
    if status:
        print(f"Audio status: {status}")
    audio_queue.put(bytes(indata))

def translate_japanese_to_english(text):
    try:
        translated = GoogleTranslator(source='ja', target='en').translate(text)
        return translated
    except Exception as e:
        return f"[Translation error: {e}]"

def start_audio_stream():
    global full_transcript
    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000, dtype='int16',
                           channels=1, callback=audio_callback):
        print("Listening...")
        silent_blocks = 0
        while True:
            data = audio_queue.get()
            is_silent, rms = is_near_silence(data)
            silent_blocks = (silent_blocks + 1) if is_silent else 0

            # Always feed Vosk so its internal state stays in sync with time
            is_final = recognizer.AcceptWaveform(data)

            if is_final:
                result = json.loads(recognizer.Result())
                text_ja = result.get("text", "").strip()
                if text_ja:
                    text_furigana = add_furigana(text_ja)
                    text_en = translate_japanese_to_english(text_ja)
                    full_transcript += f"{text_furigana}\n→ {text_en}\n\n"
                    render_full(full_transcript)
            else:
                # Only show partials when we are NOT in a silence run
                if silent_blocks < SILENCE_HANG:
                    partial = json.loads(recognizer.PartialResult()).get("partial", "")
                    if partial:
                        render_full(full_transcript + partial)

def _render_full(text: str):
    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.insert(tk.END, text)
    output_text.see(tk.END)

def render_full(text: str):
    root.after(0, _render_full, text)

def make_readonly(text):
    def no_edit(_): return "break"  # swallow edits
    for seq in ("<Key>", "<<Cut>>", "<<Paste>>", "<<Undo>>", "<<Redo>>"):
        text.bind(seq, no_edit)
    # let copy / select-all pass through
    text.bind("<Control-c>", lambda e: None)
    text.bind("<Command-c>", lambda e: None)
    text.bind("<Control-a>", lambda e: (text.tag_add("sel", "1.0", "end-1c"), "break"))
    text.bind("<Command-a>", lambda e: (text.tag_add("sel", "1.0", "end-1c"), "break"))

root = tk.Tk()
root.title("🎙️ Japanese Live Transcription + Translation")
root.geometry("1000x500")
root.configure(bg="black")

frame = tk.Frame(root, bg="black")
frame.pack(padx=10, pady=10, expand=True, fill=tk.BOTH)

scrollbar = tk.Scrollbar(frame)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

output_text = tk.Text(frame, font=("Consolas", 18), fg="#00FF00", bg="black",
                      wrap=tk.WORD, yscrollcommand=scrollbar.set)
output_text.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
make_readonly(output_text)

scrollbar.config(command=output_text.yview)


# Start the transcription thread
threading.Thread(target=start_audio_stream, daemon=True).start()

# Run the GUI loop
root.mainloop()

import os
import wave
import uuid
import numpy as np

def generate_test_audio_files():
    """Génère quelques fichiers audio de test avec différents timings"""
    
    test_audio_dir = "static/test_audio"
    os.makedirs(test_audio_dir, exist_ok=True)
    
    # Paramètres audio
    sample_rate = 8000  # 8kHz
    sample_width = 2    # 16-bit
    channels = 1        # Mono
    
    # Générer différents fichiers avec différents timings
    test_files = [
        {"duration": 2.0, "frequency": 440, "timing_ms": 1000},   # 1 seconde après début
        {"duration": 1.5, "frequency": 880, "timing_ms": 3500},   # 3.5 secondes après début
        {"duration": 3.0, "frequency": 660, "timing_ms": 6000},   # 6 secondes après début
    ]
    
    for i, config in enumerate(test_files):
        # Générer un signal sinusoïdal simple
        duration = config["duration"]
        frequency = config["frequency"]
        timing_ms = config["timing_ms"]
        
        # Créer le signal audio
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        # Signal sinusoïdal avec fade in/out pour éviter les clics
        signal = np.sin(2 * np.pi * frequency * t)
        
        # Appliquer un fade in/out
        fade_samples = int(0.05 * sample_rate)  # 50ms de fade
        if len(signal) > 2 * fade_samples:
            # Fade in
            signal[:fade_samples] *= np.linspace(0, 1, fade_samples)
            # Fade out
            signal[-fade_samples:] *= np.linspace(1, 0, fade_samples)
        
        # Normaliser et convertir en 16-bit
        signal = (signal * 0.3 * 32767).astype(np.int16)
        
        # Nom de fichier avec timing
        filename = f"{uuid.uuid4()}-{timing_ms}.wav"
        filepath = os.path.join(test_audio_dir, filename)
        
        # Écrire le fichier WAV
        with wave.open(filepath, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(signal.tobytes())
        
        print(f"Créé: {filename} ({duration}s, {frequency}Hz, timing: {timing_ms}ms)")

if __name__ == "__main__":
    generate_test_audio_files()
    print("Fichiers audio de test générés avec succès!")
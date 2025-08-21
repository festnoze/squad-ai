# Background Noise Implementation Summary

This document summarizes the implementation of continuous background noise mixing for synthesized audio in the OutgoingAudioManager.

## What Was Implemented

### 1. Configuration Support
- Added `BACKGROUND_NOISE_ENABLED=True` to control the feature
- Added `BACKGROUND_NOISE_VOLUME=0.1` to control background noise volume (10% of speech volume)
- Added corresponding EnvHelper methods:
  - `get_background_noise_enabled()`
  - `get_background_noise_volume()`

### 2. Audio Mixing Utility (`app/utils/audio_mixer.py`)
- **AudioMixer class** with comprehensive PCM audio mixing capabilities:
  - `load_background_noise()` - Loads background noise from PCM files
  - `mix_audio_with_background()` - Mixes speech with background noise
  - `loop_audio_to_length()` - Loops background noise to match speech duration
  - `adjust_volume()` - Controls audio volume levels
  - `_mix_pcm_audio()` - Core audio mixing algorithm
  - Supports 8-bit and 16-bit PCM audio formats
  - Handles mono audio at configurable sample rates

### 3. OutgoingAudioManager Integration
- **Initialization**: 
  - Loads AudioMixer instance when background noise is enabled
  - Attempts to load background noise from:
    1. `static/internal/background_noise.pcm` (preferred)
    2. `static/internal/waiting_music.pcm` (fallback)
  - Gracefully disables feature if no background noise file is found

- **Audio Processing Pipeline**:
  - Added `_apply_background_noise_if_enabled()` helper method
  - Background noise is applied to all final audio output:
    - Cached audio from `synthesize_next_audio_chunk_async()`
    - Combined audio parts
    - Fallback synthesis results
  - **Clean cache strategy**: Audio is cached WITHOUT background noise, allowing for consistent mixing

### 4. Background Noise Source
- **Primary**: Uses generated `static/internal/white_noise.pcm` (8KB, 0.5 seconds)
  - High-quality Gaussian white noise at 15% amplitude
  - Optimized for seamless looping and speech masking
  - 16-bit signed PCM, 8kHz, mono format
- **Fallback options**: 
  1. Custom `static/internal/background_noise.pcm` 
  2. Existing `static/internal/waiting_music.pcm` (317KB)
- Automatically selects the first available file in priority order

## Technical Benefits

### Audio Quality Improvements
- **Masking digital artifacts**: Background noise helps mask compression artifacts and digital silence
- **Natural audio baseline**: Provides consistent audio presence that sounds more natural
- **Improved perceived quality**: Human ears perceive audio with subtle background noise as higher quality

### Implementation Benefits
- **Configurable**: Can be enabled/disabled via environment variables
- **Volume control**: Background noise volume is adjustable (default 10%)
- **Performance optimized**: Background noise is pre-loaded once at startup
- **Cache-friendly**: Clean audio is cached, background noise applied at output
- **Error resilient**: Falls back gracefully if background noise fails to load or mix

### Integration Benefits
- **Non-intrusive**: Doesn't modify existing audio synthesis logic
- **Compatible**: Works with existing caching and synthesis pipeline
- **Flexible**: Can use any PCM background noise file
- **Maintainable**: Separated concerns with dedicated AudioMixer class

## Configuration Options

```env
# Enable/disable background noise mixing
BACKGROUND_NOISE_ENABLED=True

# Control background noise volume (0.0 to 1.0)
# 0.1 = 10% of speech volume (recommended)
BACKGROUND_NOISE_VOLUME=0.1
```

## Usage in Production

1. **Enable the feature**: Set `BACKGROUND_NOISE_ENABLED=True`
2. **Adjust volume**: Tune `BACKGROUND_NOISE_VOLUME` (start with 0.1)
3. **Custom background noise**: Replace `static/internal/waiting_music.pcm` with subtle background noise
4. **Monitor performance**: Background noise adds minimal CPU overhead

## File Structure

```
app/
├── utils/
│   └── audio_mixer.py          # New: Audio mixing utilities
├── managers/
│   └── outgoing_audio_manager.py  # Modified: Added background noise integration
└── utils/
    └── envvar.py               # Modified: Added configuration methods

static/internal/
├── white_noise.pcm             # Primary: Generated white noise for background audio
├── waiting_music.pcm           # Fallback: Existing waiting music file  
└── background_noise.pcm        # Optional: Custom background noise file
```

The implementation successfully adds continuous background noise to all synthesized audio while maintaining the existing audio processing pipeline and caching functionality.
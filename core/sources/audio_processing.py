import logging
import numpy as np

try:
    from scipy.signal import butter, lfilter

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    import noisereduce as nr

    HAS_NOISEREDUCE = True
except ImportError:
    HAS_NOISEREDUCE = False

try:
    import pyloudnorm as pyln

    HAS_PYLOUDNORM = True
except ImportError:
    HAS_PYLOUDNORM = False

logger = logging.getLogger(__name__)


class AudioEnhancer:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.meter = None
        self._check_dependencies()

        if HAS_PYLOUDNORM:
            self.meter = pyln.Meter(sample_rate)

    def _check_dependencies(self):
        missing = []
        if not HAS_SCIPY:
            missing.append("scipy")
        if not HAS_NOISEREDUCE:
            missing.append("noisereduce")
        if not HAS_PYLOUDNORM:
            missing.append("pyloudnorm")
        if missing:
            logger.warning(
                f"Audio enhancement dependencies missing: {', '.join(missing)}. Stages will be skipped."
            )

    def butter_highpass(self, cutoff, fs, order=5):
        nyq = 0.5 * fs
        normal_cutoff = cutoff / nyq
        b, a = butter(order, normal_cutoff, btype="high", analog=False)
        return b, a

    def highpass_filter(self, data, cutoff=80.0):
        if not HAS_SCIPY:
            return data
        b, a = self.butter_highpass(cutoff, self.sample_rate)
        return lfilter(b, a, data)

    def denoise(self, data):
        if not HAS_NOISEREDUCE:
            return data
        try:
            return nr.reduce_noise(
                y=data, sr=self.sample_rate, prop_decrease=0.8, n_jobs=1
            )
        except Exception as e:
            logger.error(f"Denoise error: {e}")
            return data

    def normalize_loudness(self, data, target_lufs=-23.0):
        if not HAS_PYLOUDNORM or self.meter is None:
            return data
        try:
            loudness = self.meter.integrated_loudness(data)
            if not np.isinf(loudness):
                return pyln.normalize.loudness(data, loudness, target_lufs)
            return data
        except Exception:
            return data

    def enhance(self, audio_array: np.ndarray) -> np.ndarray:
        """
        Applies a 3-stage audio processing pipeline:
        1. High-pass filter at 80 Hz
        2. Neural noise suppression
        3. EBU R128 loudness normalization

        Input audio should be float32 between -1.0 and 1.0.
        """
        if len(audio_array) == 0:
            return audio_array

        y = self.highpass_filter(audio_array, cutoff=80.0)
        y = self.denoise(y)
        y = self.normalize_loudness(y, target_lufs=-23.0)

        return y.astype(np.float32)

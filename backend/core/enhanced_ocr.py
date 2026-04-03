"""
Enhanced OCR with Image Preprocessing

Multi-strategy OCR for best text extraction quality:
1. Native text extraction (PDFs with embedded text)
2. Tesseract with image preprocessing (scanned documents)
3. Cloud OCR fallback (Google Vision API - optional)

Image preprocessing improvements:
- Grayscale conversion
- Contrast enhancement
- Noise reduction
- Deskewing
- Binarization
"""
from typing import Optional, Dict, Any
from pathlib import Path
import os

from .quiet import quiet_print

try:
    from PIL import Image, ImageEnhance, ImageFilter
    from PIL import ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import numpy as np
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class EnhancedOCR:
    """
    Multi-strategy OCR with preprocessing

    Strategies (in order):
    1. Native text extraction (PDFs)
    2. Tesseract with preprocessing
    3. Cloud OCR (if API key provided)
    """

    def __init__(self, use_cloud_ocr: bool = False, google_api_key: Optional[str] = None):
        """
        Initialize enhanced OCR

        Args:
            use_cloud_ocr: Whether to use cloud OCR as fallback
            google_api_key: Google Cloud Vision API key (optional)
        """
        self.use_cloud_ocr = use_cloud_ocr
        self.google_api_key = google_api_key or os.getenv('GOOGLE_VISION_API_KEY')

        # Check dependencies
        if not TESSERACT_AVAILABLE:
            quiet_print("Warning: pytesseract not available, OCR quality will be reduced")
        if not PIL_AVAILABLE:
            quiet_print("Warning: PIL not available, image preprocessing disabled")

    def extract_text(self, file_path: str) -> str:
        """
        Extract text using best available method

        Args:
            file_path: Path to image or PDF file

        Returns:
            Extracted text
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Strategy 1: Native PDF text extraction
        if path.suffix.lower() == '.pdf' and PYMUPDF_AVAILABLE:
            native_text = self._extract_native_pdf(file_path)
            if self._is_good_quality(native_text):
                quiet_print(f"   Extracted native PDF text ({len(native_text)} chars)")
                return native_text

        # Strategy 2: Tesseract with preprocessing
        if TESSERACT_AVAILABLE and PIL_AVAILABLE:
            preprocessed_text = self._ocr_with_preprocessing(file_path)
            if self._is_good_quality(preprocessed_text):
                quiet_print(f"   OCR with preprocessing ({len(preprocessed_text)} chars)")
                return preprocessed_text

        # Strategy 3: Cloud OCR fallback
        if self.use_cloud_ocr and self.google_api_key:
            cloud_text = self._cloud_ocr(file_path)
            if cloud_text:
                quiet_print(f"   Cloud OCR ({len(cloud_text)} chars)")
                return cloud_text

        # Fallback: basic Tesseract without preprocessing
        if TESSERACT_AVAILABLE:
            basic_text = self._basic_ocr(file_path)
            quiet_print(f"  Warning  Basic OCR (quality may be low, {len(basic_text)} chars)")
            return basic_text

        raise RuntimeError("No OCR method available - install pytesseract and PIL")

    def _extract_native_pdf(self, pdf_path: str) -> str:
        """
        Extract native text from PDF (if available)

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text
        """
        if not PYMUPDF_AVAILABLE:
            return ""

        try:
            doc = fitz.open(pdf_path)
            text_parts = []

            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)

            doc.close()

            return "\n\n".join(text_parts)

        except Exception as e:
            quiet_print(f"  Warning: Native PDF extraction failed: {e}")
            return ""

    def _ocr_with_preprocessing(self, file_path: str) -> str:
        """
        OCR with image preprocessing for better quality

        Preprocessing steps:
        1. Convert to grayscale
        2. Increase contrast
        3. Denoise
        4. Deskew (if needed)
        5. Binarize (threshold)

        Args:
            file_path: Path to image or PDF file

        Returns:
            Extracted text
        """
        if not PIL_AVAILABLE or not TESSERACT_AVAILABLE:
            return ""

        try:
            # Open image (or convert PDF to image)
            if Path(file_path).suffix.lower() == '.pdf':
                img = self._pdf_to_image(file_path)
            else:
                img = Image.open(file_path)

            # Preprocessing pipeline
            img = self._preprocess_image(img)

            # OCR with optimal settings
            text = pytesseract.image_to_string(
                img,
                config='--psm 6 --oem 3'  # PSM 6: uniform block, OEM 3: best mode
            )

            return text.strip()

        except Exception as e:
            quiet_print(f"  Warning: Preprocessing OCR failed: {e}")
            return ""

    def _preprocess_image(self, img: 'Image.Image') -> 'Image.Image':
        """
        Preprocess image for better OCR

        Args:
            img: PIL Image

        Returns:
            Preprocessed PIL Image
        """
        # Convert to grayscale
        if img.mode != 'L':
            img = img.convert('L')

        # Increase contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)

        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)

        # Denoise (median filter)
        img = img.filter(ImageFilter.MedianFilter(size=3))

        # Binarization (Otsu's method approximation)
        img = ImageOps.autocontrast(img)
        threshold = 140  # Adjust based on testing
        img = img.point(lambda x: 0 if x < threshold else 255, '1')

        # Deskew if OpenCV available
        if CV2_AVAILABLE:
            img = self._deskew_image(img)

        return img

    def _deskew_image(self, img: 'Image.Image') -> 'Image.Image':
        """
        Deskew image to correct rotation

        Args:
            img: PIL Image

        Returns:
            Deskewed PIL Image
        """
        try:
            # Convert PIL to numpy array
            img_array = np.array(img)

            # Detect text orientation
            coords = np.column_stack(np.where(img_array == 0))
            if len(coords) == 0:
                return img

            angle = cv2.minAreaRect(coords)[-1]

            # Correct angle
            if angle < -45:
                angle = 90 + angle
            elif angle > 45:
                angle = angle - 90

            # Rotate if needed
            if abs(angle) > 0.5:  # Only rotate if significant skew
                (h, w) = img_array.shape
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated = cv2.warpAffine(
                    img_array,
                    M,
                    (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE
                )
                return Image.fromarray(rotated)

            return img

        except Exception as e:
            quiet_print(f"  Warning: Deskewing failed: {e}")
            return img

    def _pdf_to_image(self, pdf_path: str, page_num: int = 0) -> 'Image.Image':
        """
        Convert PDF page to image

        Args:
            pdf_path: Path to PDF file
            page_num: Page number to convert (0-indexed)

        Returns:
            PIL Image
        """
        if PYMUPDF_AVAILABLE:
            # Use PyMuPDF for conversion
            doc = fitz.open(pdf_path)
            page = doc[min(page_num, len(doc) - 1)]

            # Render at 300 DPI for good OCR quality
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))

            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()

            return img
        else:
            raise RuntimeError("PyMuPDF required for PDF to image conversion")

    def _basic_ocr(self, file_path: str) -> str:
        """
        Basic OCR without preprocessing (fallback)

        Args:
            file_path: Path to image file

        Returns:
            Extracted text
        """
        if not TESSERACT_AVAILABLE:
            return ""

        try:
            if Path(file_path).suffix.lower() == '.pdf':
                img = self._pdf_to_image(file_path)
            else:
                img = Image.open(file_path)

            text = pytesseract.image_to_string(img)
            return text.strip()

        except Exception as e:
            quiet_print(f"  Warning: Basic OCR failed: {e}")
            return ""

    def _cloud_ocr(self, file_path: str) -> str:
        """
        Cloud OCR using Google Cloud Vision API

        Args:
            file_path: Path to image file

        Returns:
            Extracted text
        """
        if not self.google_api_key:
            return ""

        try:
            from google.cloud import vision
            import io

            # Initialize client
            client = vision.ImageAnnotatorClient()

            # Read image
            with io.open(file_path, 'rb') as image_file:
                content = image_file.read()

            image = vision.Image(content=content)

            # Perform OCR
            response = client.document_text_detection(image=image)

            if response.error.message:
                raise Exception(response.error.message)

            return response.full_text_annotation.text

        except ImportError:
            quiet_print("  Warning: google-cloud-vision not installed")
            return ""
        except Exception as e:
            quiet_print(f"  Warning: Cloud OCR failed: {e}")
            return ""

    def _is_good_quality(self, text: str, min_length: int = 100,
                        min_alpha_ratio: float = 0.7) -> bool:
        """
        Check if extracted text is good quality

        Args:
            text: Extracted text
            min_length: Minimum character length
            min_alpha_ratio: Minimum ratio of alphabetic characters

        Returns:
            True if quality is good
        """
        if not text or len(text.strip()) < min_length:
            return False

        # Check ratio of alphabetic characters
        alpha_chars = sum(c.isalpha() for c in text)
        total_chars = len(text.replace(' ', '').replace('\n', ''))

        if total_chars == 0:
            return False

        alpha_ratio = alpha_chars / total_chars

        return alpha_ratio >= min_alpha_ratio

    def extract_with_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        Extract text with quality metadata

        Args:
            file_path: Path to file

        Returns:
            Dictionary with text and metadata
        """
        text = self.extract_text(file_path)

        # Calculate quality metrics
        alpha_chars = sum(c.isalpha() for c in text)
        total_chars = len(text.replace(' ', '').replace('\n', ''))
        alpha_ratio = alpha_chars / total_chars if total_chars > 0 else 0

        words = text.split()
        avg_word_length = sum(len(w) for w in words) / len(words) if words else 0

        return {
            'text': text,
            'metadata': {
                'char_count': len(text),
                'word_count': len(words),
                'alpha_ratio': alpha_ratio,
                'avg_word_length': avg_word_length,
                'quality': 'good' if alpha_ratio > 0.7 else 'fair' if alpha_ratio > 0.5 else 'poor'
            }
        }


# Convenience function
def extract_text_enhanced(file_path: str, use_cloud: bool = False) -> str:
    """
    Quick function for enhanced text extraction

    Args:
        file_path: Path to file
        use_cloud: Whether to use cloud OCR as fallback

    Returns:
        Extracted text
    """
    ocr = EnhancedOCR(use_cloud_ocr=use_cloud)
    return ocr.extract_text(file_path)

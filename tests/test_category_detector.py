"""Tests for core.category_detector — keyword-based category detection."""
from core.category_detector import detect_category


class TestDetectCategory:
    def test_empty_text_returns_general(self):
        assert detect_category("") == "general"

    def test_wig_keywords(self):
        assert detect_category("这个假发真好看，发量也很多") == "wig"

    def test_makeup_keywords(self):
        assert detect_category("这个口红颜色好看，化妆效果也不错") == "makeup"

    def test_skincare_keywords(self):
        assert detect_category("面膜用完补水效果很好，精华也好吸收") == "skincare"

    def test_clothing_keywords(self):
        assert detect_category("这件衣服穿搭很显瘦") == "clothing"

    def test_no_keywords_returns_general(self):
        assert detect_category("今天天气真好啊") == "general"

    def test_multiple_categories_picks_highest(self):
        # 3 makeup hits vs 1 skincare hit
        text = "口红唇膏腮红配合面膜使用"
        result = detect_category(text)
        assert result == "makeup"

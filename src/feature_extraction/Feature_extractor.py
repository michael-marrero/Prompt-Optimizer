import re
import math
import string
import pandas as pd
import nltk
from nltk.tokenize import sent_tokenize

_NLTK_PUNKT_READY = False


def _ensure_nltk_sentence_tokenizer() -> None:
    """NLTK 3.9+ expects ``punkt_tab`` for ``sent_tokenize``; older installs used ``punkt`` only."""
    global _NLTK_PUNKT_READY
    if _NLTK_PUNKT_READY:
        return
    for package in ("punkt_tab", "punkt"):
        nltk.download(package, quiet=True)
    _NLTK_PUNKT_READY = True


def _safe_text(text) -> str:
    if text is None:
        return ""

    if isinstance(text, float) and math.isnan(text):
        return ""

    return str(text).strip()

class PromptFeatureExtractor:
    def __init__(self ):
        #Initialize the feature extractor.
        # -------------------------
        # Keyword groups
        # -------------------------
        self.code_keywords = [
            "python", "java", "c++", "javascript", "function", "class",
            "method", "variable", "array", "list", "dictionary", "dict",
            "recursion", "loop", "bug", "error", "traceback", "compile",
            "runtime", "algorithm", "code", "program", "script", "return",
            "debug", "exception", "syntax", "terminal", "bash", "api"
        ]
        self.math_keywords = [
            "solve", "equation", "derivative", "integral", "matrix",
            "probability", "theorem", "proof", "calculate", "simplify",
            "factor", "limit", "graph", "function", "variable",
            "algebra", "geometry", "statistics", "mean", "variance",
            "standard deviation", "linear", "quadratic"
        ]
        self.reasoning_keywords = [
            "explain", "why", "how", "reason", "analyze", "infer",
            "conclude", "therefore", "because", "compare", "evaluate",
            "determine", "justify", "which is better", "tradeoff",
            "pros and cons"
        ]
        self.writing_keywords = [
            "essay", "paragraph", "rewrite", "summarize", "summary",
            "tone", "thesis", "introduction", "conclusion", "draft",
            "email", "speech", "presentation", "outline", "revise",
            "format", "make it sound"
        ]
        self.factual_keywords = [
            "what", "who", "when", "where", "define", "definition",
            "list", "name", "identify", "describe", "fact", "facts"
        ]
        self.instruction_keywords = [
            "step by step", "json", "table", "bullet", "concise",
            "detailed", "explain your answer", "show work", "only",
            "must", "should", "include", "do not", "don't", "without",
            "exactly"
        ]
        self.debugging_keywords = [
            "error", "traceback", "exception", "bug", "fix", "broken",
            "issue", "doesn't work", "does not work", "failed", "invalid",
            "crash", "crashing", "problem"
        ]
        self.data_keywords = [
            "csv", "dataframe", "dataset", "rows", "columns", "json",
            "database", "sql", "pandas", "numpy", "features", "label",
            "train", "test", "validation", "model", "classifier"
        ]
        self.constraint_keywords = [
            "must", "should", "only", "don't", "do not", "without",
            "exactly", "at least", "at most", "no more than", "include",
            "exclude", "required", "cannot", "never"
        ]

        # Store all keyword groups together so helper methods can loop over them later
        self.keyword_groups = {
            "code": self.code_keywords,
            "math": self.math_keywords,
            "reasoning": self.reasoning_keywords,
            "writing": self.writing_keywords,
            "factual": self.factual_keywords,
            "instruction": self.instruction_keywords,
            "debugging": self.debugging_keywords,
            "data": self.data_keywords,
            "constraint": self.constraint_keywords,
        }

    def extract(self, text: str) -> dict:
        text = _safe_text(text)
        features = {}
        features.update(self._basic_text_features(text))
        features.update(self._symbol_features(text))
        features.update(self._keyword_features(text))
        features.update(self._complexity_features(text))
        features.update(self._constraint_features(text))
        return features

    def _basic_text_features(self, text: str) -> dict:
        c_count = len(text)
        words = text.split()
        seen_words = set()
        word_count = len(words)
        unique_words = 0
        avg_word_length = 0.0
        max_word_length = 0
        for word in words:
            if word.lower() not in seen_words:
                seen_words.add(word.lower())
                unique_words += 1
            wl = len(word)
            if wl > max_word_length:
                max_word_length = wl
            avg_word_length += wl
        if word_count:
            avg_word_length /= word_count
        number_count = len(re.findall(r"\d+", text))
        _ensure_nltk_sentence_tokenizer()
        sentences_count = len(sent_tokenize(text))
        return {
            "char_count": c_count,
            "word_count": word_count,
            "unique_words_count": unique_words,
            "avg_word_length": avg_word_length,
            "max_word_length": max_word_length,
            "number_count": number_count,
            "sentences_count": sentences_count
        }

    def _symbol_features(self, text: str) -> dict:
        question_mark_count = 0
        exclamation_count = 0
        period_count = 0
        comma_count = 0
        colon_count = 0
        semicolon_count = 0
        quote_count = 0
        parentheses_count = 0
        bracket_count = 0
        brace_count = 0
        equals_count = 0
        operator_count = 0
        for char in text:
            if char == "?":
                question_mark_count += 1
            elif char == "!":
                exclamation_count += 1
            elif char == ".":
                period_count += 1
            elif char == ",":
                comma_count += 1
            elif char == ":":
                colon_count += 1
            elif char == ";":
                semicolon_count += 1
            elif char == "'" or char == '"':
                quote_count += 1
            elif char == "(" or char == ")":
                parentheses_count += 1
            elif char == "[" or char == "]":
                bracket_count += 1
            elif char == "{" or char == "}":
                brace_count += 1
            elif char == "=":
                equals_count += 1
            elif char in ["+", "-", "*", "/", "%", "^", "<", ">"]:
                operator_count += 1
        return {
            "question_mark_count": question_mark_count,
            "exclamation_count": exclamation_count,
            "period_count": period_count,
            "comma_count": comma_count,
            "colon_count": colon_count,
            "semicolon_count": semicolon_count,
            "quote_count": quote_count,
            "parentheses_count": parentheses_count,
            "bracket_count": bracket_count,
            "brace_count": brace_count,
            "equals_count": equals_count,
            "operator_count": operator_count,
        }
    def _keyword_features(self, text: str) -> dict:
        text = text.lower()

        code_keyword_count = 0
        math_keyword_count = 0
        reasoning_keyword_count = 0
        writing_keyword_count = 0
        factual_keyword_count = 0
        instruction_keyword_count = 0
        debugging_keyword_count = 0
        data_keyword_count = 0
        constraint_keyword_count = 0

        for keyword in self.code_keywords:
            if keyword in text:
                code_keyword_count += 1

        for keyword in self.math_keywords:
            if keyword in text:
                math_keyword_count += 1

        for keyword in self.reasoning_keywords:
            if keyword in text:
                reasoning_keyword_count += 1

        for keyword in self.writing_keywords:
            if keyword in text:
                writing_keyword_count += 1

        for keyword in self.factual_keywords:
            if keyword in text:
                factual_keyword_count += 1

        for keyword in self.instruction_keywords:
            if keyword in text:
                instruction_keyword_count += 1

        for keyword in self.debugging_keywords:
            if keyword in text:
                debugging_keyword_count += 1

        for keyword in self.data_keywords:
            if keyword in text:
                data_keyword_count += 1

        for keyword in self.constraint_keywords:
            if keyword in text:
                constraint_keyword_count += 1
        return {
            "has_code_keywords": 1 if code_keyword_count > 0 else 0,
            "code_keyword_count": code_keyword_count,

            "has_math_keywords": 1 if math_keyword_count > 0 else 0,
            "math_keyword_count": math_keyword_count,

            "has_reasoning_keywords": 1 if reasoning_keyword_count > 0 else 0,
            "reasoning_keyword_count": reasoning_keyword_count,

            "has_writing_keywords": 1 if writing_keyword_count > 0 else 0,
            "writing_keyword_count": writing_keyword_count,

            "has_factual_keywords": 1 if factual_keyword_count > 0 else 0,
            "factual_keyword_count": factual_keyword_count,

            "has_instruction_keywords": 1 if instruction_keyword_count > 0 else 0,
            "instruction_keyword_count": instruction_keyword_count,

            "has_debugging_keywords": 1 if debugging_keyword_count > 0 else 0,
            "debugging_keyword_count": debugging_keyword_count,

            "has_data_keywords": 1 if data_keyword_count > 0 else 0,
            "data_keyword_count": data_keyword_count,

            "has_constraint_keywords": 1 if constraint_keyword_count > 0 else 0,
            "constraint_keyword_count": constraint_keyword_count,
        }
    def _complexity_features(self, text: str) -> dict:
        question_count = 0
        has_multiple_q = False
        has_numbers = False
        number_count = 0
        has_equations = False
        short_query = False
        long_query = False
        complexity_score = 0
        word_c = len(text.split())
        if word_c < 10:
            short_query = True
        elif word_c >= 40:
            long_query = True
        question_count = text.count("?")

        if question_count > 1:
            has_multiple_q = True

        numbers = re.findall(r'\d+', text)
        number_count = len(numbers)

        if number_count > 0:
            has_numbers = True

        if "=" in text:
            has_equations = True
        elif number_count > 0:
            for char in text:
                if char in ["+", "-", "*", "/", "%", "^", "<", ">"]:
                    has_equations = True
        # rough complexity score
        complexity_score += word_c * 0.1
        complexity_score += question_count * 1.0
        complexity_score += number_count * 0.5
        if has_multiple_q:
            complexity_score += 2
        if has_equations:
            complexity_score += 2
        if long_query:
            complexity_score += 3
        if short_query:
            complexity_score -= 1
        return {
            "question_count": question_count,
            "has_multiple_questions": 1 if has_multiple_q else 0,
            "has_numbers": 1 if has_numbers else 0,
            "number_count": number_count,
            "has_equations": 1 if has_equations else 0,
            "short_query": 1 if short_query else 0,
            "long_query": 1 if long_query else 0,
            "complexity_score": complexity_score,
        }

    def _constraint_features(self, text: str) -> dict:
        text = text.lower()

        constraint_count = 0
        has_constraints = False
        has_negative_constraint = False
        has_format_requirement = False

        negative_constraints = [
            "do not", "don't", "never", "without", "cannot", "can't", "no "
        ]

        format_requirements = [
            "json", "table", "bullet", "bullets", "format", "exactly",
            "return", "only", "list", "paragraph", "csv"
        ]

        for keyword in self.constraint_keywords:
            if keyword in text:
                constraint_count += 1

        for keyword in negative_constraints:
            if keyword in text:
                has_negative_constraint = True

        for keyword in format_requirements:
            if keyword in text:
                has_format_requirement = True

        if constraint_count > 0:
            has_constraints = True

        return {
            "constraint_count": constraint_count,
            "has_constraints": 1 if has_constraints else 0,
            "has_negative_constraint": 1 if has_negative_constraint else 0,
            "has_format_requirement": 1 if has_format_requirement else 0,
        }
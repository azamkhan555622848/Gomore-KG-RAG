"""
Ollama Interface for Answer Generation
Handles communication with Ollama for query answering
"""

import requests
from typing import List, Optional, Dict
from loguru import logger

from shared.config import get_query_config
from shared.prompts import (
    format_answer_generation_prompt,
    format_answer_generation_with_citations_prompt,
    format_query_entity_extraction_prompt
)
from shared.utils import extract_json_from_text


class OllamaInterface:
    """Interface for Ollama LLM"""

    def __init__(self):
        self.config = get_query_config()
        self.host = self.config.ollama_host.rstrip('/')
        self.model = self.config.answer_model
        self.chat_endpoint = f"{self.host}/api/chat"

        logger.info(f"OllamaInterface initialized. Model: {self.model}")

    def generate_answer(
        self,
        question: str,
        context: str,
        entities: List[str] = None,
        include_citations: bool = None
    ) -> str:
        """
        Generate answer to question using context

        Args:
            question: User question
            context: Context from graph/documents
            entities: List of entity names in context
            include_citations: Whether to include citations

        Returns:
            Generated answer
        """
        if include_citations is None:
            include_citations = self.config.enable_citations

        # Format prompt
        if include_citations and entities:
            prompt = format_answer_generation_with_citations_prompt(
                context, entities, question
            )
        else:
            prompt = format_answer_generation_prompt(context, question)

        # Generate response
        response = self._chat(prompt)

        return response

    def extract_query_entities(self, query: str) -> List[str]:
        """
        Extract entities from user query

        Args:
            query: User query

        Returns:
            List of entity names
        """
        prompt = format_query_entity_extraction_prompt(query)

        response = self._chat(
            prompt,
            max_tokens=256,
            temperature=0.3
        )

        # Parse JSON response
        entities = extract_json_from_text(response)

        if entities and isinstance(entities, list):
            return [str(e).strip() for e in entities if str(e).strip()]

        return []

    def _chat(
        self,
        prompt: str,
        max_tokens: int = None,
        temperature: float = None,
        system: str = None
    ) -> str:
        """
        Send chat request to Ollama

        Args:
            prompt: User prompt
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            system: Optional system message

        Returns:
            Generated response
        """
        if max_tokens is None:
            max_tokens = self.config.max_answer_tokens
        if temperature is None:
            temperature = self.config.temperature

        try:
            # Prepare messages
            messages = []

            if system:
                messages.append({"role": "system", "content": system})

            messages.append({"role": "user", "content": prompt})

            # Make request
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": self.config.stream_response,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature
                }
            }

            response = requests.post(
                self.chat_endpoint,
                json=payload,
                timeout=120
            )

            response.raise_for_status()

            # Extract response
            result = response.json()

            if "message" in result and "content" in result["message"]:
                return result["message"]["content"]
            else:
                logger.error(f"Unexpected response format: {result}")
                return ""

        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API error: {e}")
            return f"Error communicating with Ollama: {e}"
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return f"Error generating answer: {e}"

    def check_connection(self) -> bool:
        """Check if Ollama is available"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False

    def list_models(self) -> List[str]:
        """List available models"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "models" in data:
                    return [model["name"] for model in data["models"]]
        except:
            pass
        return []


if __name__ == "__main__":
    # Test Ollama interface
    from shared.utils import setup_logging

    setup_logging(level="INFO")

    ollama = OllamaInterface()

    # Check connection
    if ollama.check_connection():
        print("✓ Ollama connection successful")

        # List models
        models = ollama.list_models()
        print(f"\nAvailable models: {', '.join(models)}")

        # Test entity extraction
        query = "Who works at Google in Mountain View?"
        entities = ollama.extract_query_entities(query)
        print(f"\nQuery: {query}")
        print(f"Extracted entities: {entities}")

        # Test answer generation
        context = "Dr. Jane Smith works for Google in Mountain View, California. She is a software engineer."
        answer = ollama.generate_answer(query, context, entities=["Jane Smith", "Google", "Mountain View"])
        print(f"\nAnswer: {answer}")

    else:
        print("✗ Cannot connect to Ollama")
        print(f"  Make sure Ollama is running at {ollama.host}")
        print("  Start Ollama: ollama serve")

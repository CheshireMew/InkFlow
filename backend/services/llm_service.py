"""
InkFlow LLM Service

Handles communication with LLM APIs (DeepSeek, OpenAI compatible).
"""

import logging
import os
from typing import Optional

from services.http_client import http_post_json
from core.exceptions import LLMError, LLMTimeoutError

logger = logging.getLogger("LLMService")


# Configuration (will be loaded from config file)
class LLMConfig:
    """LLM configuration."""
    api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    max_tokens: int = 2048
    

_config = LLMConfig()


def configure_llm(api_key: str = "", base_url: str = "", model: str = ""):
    """Configure LLM settings."""
    if api_key:
        _config.api_key = api_key
    if base_url:
        _config.base_url = base_url
    if model:
        _config.model = model



class LLMService:
    """Service for LLM interactions."""
    
    def __init__(self):
        self.config = _config

    async def generate_content(
        self,
        user_prompt: str,
        system_prompt: str = "You are a helpful writing assistant.",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> str:
        """
        Generate content using LLM.
        """
        if not self.config.api_key:
            raise LLMError("LLM API key not configured", code="LLM_NO_API_KEY")
        
        url = f"{self.config.base_url}/chat/completions"
        
        payload = {
            "model": model or self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens or self.config.max_tokens
        }
        
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            # === LLM TRAFFIC BUS: OUTBOUND ===
            logger.info(f"\n{'='*20} [LLM REQUEST BUS] {'='*20}")
            logger.info(f"MODEL: {payload.get('model')}")
            logger.info(f"SYSTEM PROMPT:\n{system_prompt}")
            logger.info(f"USER PROMPT:\n{user_prompt}")
            logger.info(f"{'='*60}\n")

            logger.debug(f"🤖 Calling LLM: {self.config.model}")
            response = await http_post_json(url, payload, headers=headers)
            
            # Parse response
            if "choices" not in response or not response["choices"]:
                raise LLMError("Invalid LLM response: no choices", code="LLM_INVALID_RESPONSE")
            
            content = response["choices"][0]["message"]["content"]
            
            # === LLM TRAFFIC BUS: INBOUND ===
            logger.info(f"\n{'='*20} [LLM RESPONSE BUS] {'='*20}")
            logger.info(f"CONTENT:\n{content}")
            logger.info(f"{'='*60}\n")

            logger.debug(f"✅ LLM response: {len(content)} chars")
            
            return content
            
        except TimeoutError:
            raise LLMTimeoutError("LLM request timed out")
        except Exception as e:
            if "rate" in str(e).lower():
                from core.exceptions import LLMRateLimitError
                raise LLMRateLimitError(f"Rate limit: {e}")
            raise LLMError(f"LLM request failed: {e}")

    async def generate_variants(
        self,
        user_prompt: str,
        system_prompt: str = "You are a helpful writing assistant.",
        n: int = 3,
        temperature: float = 0.7,
        model: Optional[str] = None
    ) -> list[str]:
        """
        Generate multiple content variants.
        """
        variants = []
        for i in range(n):
            # Increase temperature spread for diversity
            temp = temperature + (i * 0.15)
            
            # Inject diversity instruction
            current_prompt = user_prompt
            if i > 0:
                instructions = [
                    "Please use a different sentence structure and tone.",
                    "Please focus on a different angle or aspect.",
                    "Please be more concise or punchy."
                ]
                # Appending to prompt to force LLM to diverge
                current_prompt += f"\n\n[System Note: Generate variation {i+1}. {instructions[i % len(instructions)]}]"

            content = await self.generate_content(
                user_prompt=current_prompt, 
                system_prompt=system_prompt,
                temperature=min(temp, 1.1), # Cap at 1.1
                model=model
            )
            variants.append(content)
        return variants


# Singleton instance
_instance = LLMService()

def get_llm_service() -> LLMService:
    """Get the LLMService singleton."""
    return _instance

# Backward compatibility wrappers (if needed)
async def generate_content(prompt: str, **kwargs) -> str:
    return await _instance.generate_content(user_prompt=prompt, **kwargs)

async def generate_variants(prompt: str, count: int = 3, **kwargs) -> list[str]:
    return await _instance.generate_variants(user_prompt=prompt, n=count, **kwargs)

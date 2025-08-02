"""
AI-related utility functions for the Discord bot.
"""
from openai import OpenAI
import os
from config import MAX_RESPONSE_TOKENS, OPENAI_API_KEY, AI_MODEL, DEFAULT_TEMPERATURE

# Set up the OpenAI API client
client = OpenAI(api_key=OPENAI_API_KEY)

async def generate_ai_response(messages, max_tokens=None, temperature=None):
    """
    Generate an AI response using the current provider.
    This function can be modified to use different AI providers in the future.
    
    Args:
        messages: List of message objects with role and content
        max_tokens: Maximum number of tokens in the response
        temperature: Creativity of the response (0.0-1.0)
        
    Returns:
        str: The generated response text
    """
    try:
        # Use default values if not specified
        if max_tokens is None:
            max_tokens = MAX_RESPONSE_TOKENS
        if temperature is None:
            temperature = DEFAULT_TEMPERATURE
            
        # Using the model specified in config
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            n=1,
            temperature=temperature
        )
        
        raw_response = response.choices[0].message.content.strip()
        finish_reason = response.choices[0].finish_reason
        
        # Check if the response was cut off due to length
        if finish_reason == "length":
            print(f"Response was truncated due to token limit")
            return raw_response + "\n\n[Note: Response was truncated due to length. Feel free to ask for more details.]"
        
        return raw_response
    except Exception as e:
        print(f"Error generating AI response: {e}")
        raise e  # Re-raise the exception to be handled by the caller

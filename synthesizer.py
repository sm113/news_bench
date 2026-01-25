"""
News Bench - Story Synthesizer (Upgraded)
=========================================
Uses LLMs with JSON-enforcement for reliable story generation.
"""

import time
import json
import re
from typing import List, Dict, Optional

# =============================================================================
# SYNTHESIS CONFIG
# =============================================================================
from config import (
    LLM_MODEL,
    LLM_PROVIDER,
    GROQ_API_KEY,
    TOGETHER_API_KEY,
    OLLAMA_HOST,
    MAX_TOKENS,
    TEMPERATURE,
    LLM_MAX_RETRIES,
    LLM_RETRY_DELAY
)
from prompts import SYNTHESIS_PROMPT
import database
import clusterer

def format_articles_for_prompt(articles: List[Dict]) -> str:
    """Format articles for inclusion in the LLM prompt."""
    formatted = []
    # Dynamically adjust preview length based on cluster size
    # Smaller clusters get more text per article
    if len(articles) <= 4:
        preview_length = 3000
    elif len(articles) <= 8:
        preview_length = 2000
    else:
        preview_length = 1500

    for article in articles:
        body_preview = article.get('lede', '')[:preview_length]
        formatted.append(f"""
[SOURCE: {article['source_name']} | LEAN: {article['source_lean']}]
Headline: {article['headline']}
Content: {body_preview}
---""")
    return "\n".join(formatted)

# =============================================================================
# LLM PROVIDERS
# =============================================================================

def call_ollama(prompt: str) -> Optional[str]:
    import requests
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",  # OLLAMA NATIVE JSON MODE
                "options": {
                    "temperature": TEMPERATURE,
                    "num_predict": MAX_TOKENS
                }
            },
            timeout=120
        )
        response.raise_for_status()
        return response.json().get('response', '')
    except Exception as e:
        print(f"Ollama error: {e}")
        return None

def call_groq(prompt: str) -> Optional[str]:
    import requests
    if not GROQ_API_KEY: return None
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"}, # GROQ JSON MODE
                "temperature": TEMPERATURE,
                "max_tokens": MAX_TOKENS
            },
            timeout=60
        )
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Groq error: {e}")
        return None

def call_together(prompt: str) -> Optional[str]:
    import requests
    if not TOGETHER_API_KEY: return None
    try:
        response = requests.post(
            "https://api.together.xyz/v1/chat/completions",
            headers={"Authorization": f"Bearer {TOGETHER_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": TEMPERATURE,
                "max_tokens": MAX_TOKENS
            },
            timeout=60
        )
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Together error: {e}")
        return None

def call_llm(prompt: str) -> Optional[str]:
    providers = {"ollama": call_ollama, "groq": call_groq, "together": call_together}
    func = providers.get(LLM_PROVIDER)
    if not func: return None

    for attempt in range(LLM_MAX_RETRIES):
        result = func(prompt)
        if result: return result
        time.sleep(LLM_RETRY_DELAY)
    return None

# =============================================================================
# RESPONSE PARSING
# =============================================================================

def clean_json_response(response: str) -> str:
    """Removes Markdown code blocks if the LLM adds them."""
    if "```" in response:
        # Regex to extract content between ```json and ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if match:
            return match.group(1)
    return response

def parse_synthesis_response(response: str) -> Dict:
    """Parse JSON response from LLM."""
    default_result = {
        'headline': '', 'consensus': '', 'left_framing': '', 
        'right_framing': '', 'center_framing': '', 'key_differences': ''
    }
    
    if not response:
        return default_result

    try:
        # Clean potential markdown
        clean_res = clean_json_response(response)
        data = json.loads(clean_res)
        
        # Merge with default to ensure all keys exist
        return {**default_result, **data}
        
    except json.JSONDecodeError as e:
        print(f"  Error parsing JSON from LLM: {e}")
        print(f"  Raw response: {response[:100]}...")
        return default_result

# =============================================================================
# SYNTHESIS PIPELINE
# =============================================================================

def synthesize_and_store_cluster(articles: List[Dict]) -> Optional[int]:
    if len(articles) < 2: return None

    sources = set(a['source_name'] for a in articles)
    leans = {a['source_lean'] for a in articles}
    print(f"\nSynthesizing cluster with {len(articles)} articles from {len(sources)} sources...")
    print(f"  Sources: {', '.join(sorted(sources))}")
    print(f"  Coverage: {', '.join(sorted(leans))}")
    print(f"  Sample: {articles[0]['headline'][:60]}...")

    # Format articles for prompt
    articles_text = format_articles_for_prompt(articles)
    prompt = SYNTHESIS_PROMPT.format(articles=articles_text)

    # Call LLM
    response = call_llm(prompt)
    if not response: return None

    # Parse response
    synthesis = parse_synthesis_response(response)
    
    if not synthesis.get('headline'):
        print("  Failed to generate valid synthesis")
        return None

    # Store in database
    story_id = database.insert_story(
        synthesized_headline=synthesis['headline'],
        consensus=synthesis['consensus'],
        left_framing=synthesis['left_framing'],
        right_framing=synthesis['right_framing'],
        center_framing=synthesis['center_framing'],
        key_differences=synthesis['key_differences'],
        article_ids=[a['id'] for a in articles]
    )

    print(f"  Created story {story_id}: {synthesis['headline'][:50]}...")
    return story_id

def run_synthesis(clusters=None) -> List[int]:
    print("\n" + "="*60 + "\nNEWS BENCH - JSON Synthesis\n" + "="*60)
    
    if clusters is None:
        clusters = clusterer.run_clustering()

    if not clusters:
        print("No clusters to synthesize")
        return []

    story_ids = []
    for i, cluster in enumerate(clusters):
        story_id = synthesize_and_store_cluster(cluster)
        if story_id: story_ids.append(story_id)
        time.sleep(1)

    return story_ids

if __name__ == "__main__":
    database.init_database()
    run_synthesis()
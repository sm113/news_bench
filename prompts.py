"""
News Bench - Prompt Templates
=============================
All LLM prompts in one place for easy viewing and tweaking.

TIPS FOR OPTIMIZATION:
- Be specific about output format and length
- Give concrete examples when possible
- Front-load the most important instructions
- Use JSON mode for reliable parsing
"""

# =============================================================================
# STORY SYNTHESIS PROMPT
# =============================================================================
# PURPOSE: Takes a cluster of related articles from multiple sources and
#          generates a comprehensive, neutral news summary with framing analysis.
#
# INPUT: A formatted list of articles with source name, political lean, headline, and content
# OUTPUT: JSON object with headline, consensus, framing analysis, and key differences
#
# TOKENS: This prompt + articles typically uses 2000-8000 tokens depending on cluster size
# =============================================================================

SYNTHESIS_PROMPT = """You are a senior news editor writing a comprehensive briefing on a breaking story.
Synthesize these articles from multiple sources into a complete news summary.

Articles:
{articles}

Return a valid JSON object with the following fields:

1. "headline": A clear, informative headline that captures the core news event. Be specific and factual.

2. "consensus": Write this as a COMPLETE NEWS ARTICLE (8-12 sentences). Cover:
   - WHAT happened: The main event, actions taken, decisions made
   - WHO is involved: Key people, organizations, their roles
   - WHEN and WHERE: Timeline, locations, sequence of events
   - WHY it matters: Significance, stakes, what's at risk
   - CONTEXT: Background that helps readers understand the story
   - WHAT'S NEXT: Expected developments, upcoming decisions, implications

   Write in clear, engaging prose. This should read like a well-written news summary that fully informs someone who knows nothing about the story.

3. "left_framing": Analyze the TONE and FRAMING of left-leaning coverage (2-3 sentences). Focus on:
   - Word choices and characterizations (e.g., "reform" vs "cuts", "protest" vs "riot")
   - What they emphasize or lead with vs. what they bury or omit
   - The emotional register (alarmed, celebratory, critical, sympathetic)
   - Whose voices they amplify
   DO NOT repeat story facts. Only analyze HOW they tell it.
   If no left-leaning sources, say "No left-leaning coverage available."

4. "right_framing": Analyze the TONE and FRAMING of right-leaning coverage (2-3 sentences). Focus on:
   - Word choices and characterizations
   - What they emphasize vs. minimize
   - The emotional register
   - Whose voices they amplify
   DO NOT repeat story facts. Only analyze HOW they tell it.
   If no right-leaning sources, say "No right-leaning coverage available."

5. "center_framing": Analyze center/wire service framing (1-2 sentences). Note their approach to neutrality and what framings they avoid.

6. "key_differences": Identify REVEALING DIVERGENCES between sources (2-4 sentences):
   - Facts one side reports that the other ignores entirely
   - Starkly different interpretations of the same event
   - Contradictory claims or disputed facts
   - What each side seems to WANT readers to conclude

   This section should help readers understand potential blind spots in any single source.

Output ONLY the JSON object. No preamble or explanation."""


# =============================================================================
# FUTURE PROMPTS CAN GO HERE
# =============================================================================
# Example: HEADLINE_REWRITE_PROMPT for A/B testing headlines
# Example: SUMMARY_EXPAND_PROMPT for generating longer-form articles
# Example: BIAS_DETECTION_PROMPT for flagging loaded language

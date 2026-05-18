import asyncio
import json
import re
import ollama
import os
import sys

# Add parent dir to path so we can import project modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_utils import TOOL_MAP, check_thread_status, get_semantic_similarities, extract_ids_regex

# CONFIGURATION - Using the tiny model for speed and memory safety
MODEL = "llama3.2:1b"

async def stage0_deduplicate(subject, body, sender, conv_id, msg_id):
    """
    Orchestrates the duplication check.
    Runs all data-gathering tools first, then asks a tiny LLM for a decision.
    """
    print(f"\n[STAGE 0] Analyzing: '{subject}' from {sender}")

    try:
        # 1. PRE-EMPTIVE TOOL GATHERING
        thread_status = check_thread_status(conv_id, sender, msg_id)
        
        extracted_ids_json = extract_ids_regex(body)
        extracted_ids = json.loads(extracted_ids_json)

        semantic_match_json = get_semantic_similarities(subject, body, sender)
        semantic_match = None
        if "No similar emails" not in semantic_match_json:
            try:
                semantic_match = json.loads(semantic_match_json)
            except Exception:
                pass

        # 2. RESOLVE SEMANTIC STATUS IN MYSQL
        semantic_status = None
        if semantic_match:
            matched_msg_id = semantic_match.get('message_id')
            matched_conv_id = semantic_match.get('conversation_id')
            if matched_msg_id or matched_conv_id:
                semantic_status = check_thread_status(matched_conv_id, sender, matched_msg_id)

        # 3. STATE MACHINE PRIORITIES (HARD-CODED SAFETY OVERRIDES)
        
        # Priority 1: Current thread has already been replied to
        if thread_status in ['MATCH_REPLIED', 'THREAD_REPLIED']:
            final_result = {
                "decision": "DUPLICATE",
                "reasoning": f"System matched this record in MySQL as already replied (Status: {thread_status})."
            }
            print(f"[DECISION]: {final_result['decision']} (Forced by DB: {thread_status})")
            return final_result

        # Priority 2: A semantically similar email has already been replied to
        if semantic_status in ['MATCH_REPLIED', 'THREAD_REPLIED']:
            final_result = {
                "decision": "DUPLICATE",
                "reasoning": f"System found a semantically identical email that has already been replied to (Similarity: {semantic_match.get('similarity', 0)}%, MySQL: {semantic_status})."
            }
            print(f"[DECISION]: {final_result['decision']} (Forced by Semantic DB Match: {semantic_status})")
            return final_result

        # Priority 3: Current thread is processed but pending reply
        if thread_status == 'MATCH_PENDING':
            final_result = {
                "decision": "DUPLICATE",
                "reasoning": f"System matched this record in MySQL as pending reply (Status: {thread_status})."
            }
            print(f"[DECISION]: {final_result['decision']} (Forced by DB: {thread_status})")
            return final_result

        # Priority 4: A semantically similar email is processed but pending reply
        if semantic_status == 'MATCH_PENDING':
            final_result = {
                "decision": "DUPLICATE",
                "reasoning": f"System found a semantically identical email that is pending reply (Similarity: {semantic_match.get('similarity', 0)}%, MySQL: {semantic_status})."
            }
            print(f"[DECISION]: {final_result['decision']} (Forced by Semantic DB Match: {semantic_status})")
            return final_result

        # Priority 5: Pure fresh inquiry
        if thread_status == "NEW" and not semantic_match:
            final_result = {
                "decision": "NEW",
                "reasoning": "Database and VectorStore are empty for this sender. Confirmed fresh inquiry."
            }
            print(f"[DECISION]: {final_result['decision']} (Confirmed Fresh)")
            return final_result

        # 2. ASK THE TINY BRAIN (Llama 3.2 1B)
        # We use a very strict prompt to prevent logic flips.
        context_prompt = f"""
        Determine if this email is a DUPLICATE of a previous message or a NEW inquiry.
        
        DATA:
        - Thread Status: {thread_status}
        - Current IDs: {json.dumps(extracted_ids)}
        - Semantic Match: {json.dumps(semantic_match) if semantic_match else "NONE"}
        
        LOGIC RULES:
        1. If Semantic Match is "NONE" and Thread Status is "NEW" -> Decision MUST be "NEW".
        2. If Current IDs are DIFFERENT from any matched IDs -> Decision MUST be "NEW".
        3. If there is an exact match in Thread or Semantic Similarity > 0.85 -> Decision is "DUPLICATE".
        
        OUTPUT FORMAT (JSON ONLY):
        {{"decision": "NEW" | "DUPLICATE", "reasoning": "Short explanation"}}
        """

        client = ollama.AsyncClient()
        response = await client.chat(
            model=MODEL,
            messages=[{"role": "user", "content": context_prompt}],
            format="json"
        )

        final_content = response['message']['content'].strip()
        print(f"[DEBUG] Raw AI Response: {final_content}")
        
        try:
            raw_result = json.loads(final_content)
            result = {k.lower(): v for k, v in raw_result.items()} 
            
            decision = result.get('decision', result.get('status', 'NEW'))
            reasoning = result.get('reasoning', result.get('reason', result.get('explanation', 'No reason provided')))
            
            # Final Safety Catch: If AI hallucinated a duplicate when facts say NEW
            if thread_status == "NEW" and not semantic_match:
                decision = "NEW"
                reasoning = "AI logic flip detected. Overridden to NEW because DB is empty."

            if 'duplicate' in str(decision).lower(): decision = "DUPLICATE"
            else: decision = "NEW"

            final_result = {"decision": decision, "reasoning": reasoning}
            print(f"[DECISION]: {final_result['decision']}")
            print(f"[REASON]:   {final_result['reasoning']}")
            return final_result

        except Exception as parse_err:
            print(f"[ERROR] JSON Parse/Normalize Error: {parse_err}")
            return {"decision": "NEW", "reasoning": "Could not normalize agent response."}

    except Exception as e:
        print(f"[ERROR] Stage 0 main process failed: {e}")
        return {"decision": "NEW", "reasoning": f"System error: {str(e)}"}

if __name__ == "__main__":
    test_email = {
        "subject": "Quick update needed",
        "body": "Hi, just checking in on the status of my shipment for TRK12345. Any news?",
        "sender": "navan@example.com",
        "conv_id": "conv_xyz_789",
        "msg_id": "msg_unique_001"
    }
    asyncio.run(stage0_deduplicate(**test_email))

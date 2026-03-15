"""LLM wrapper service – Ollama local inference with RAG support."""

from __future__ import annotations

import json
import hashlib
from typing import Any, Optional

import httpx
import numpy as np
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

settings = get_settings()

# ── FAISS vector store (lazy init) ──────────────────────────
_faiss_index = None
_vector_store: dict[str, dict] = {}  # hash -> {text, metadata, embedding}


def _get_faiss_index(dim: int = 768):
    global _faiss_index
    if _faiss_index is None:
        import faiss
        _faiss_index = faiss.IndexFlatIP(dim)
    return _faiss_index


# ── System prompts ──────────────────────────────────────────
SYSTEM_PROMPTS = {
    "post_generator": (
        "You are an expert LinkedIn content strategist. Generate engaging, professional "
        "LinkedIn posts that maximize engagement. Use natural language, avoid spam-like "
        "phrases, and include relevant insights. Adapt tone to the target audience. "
        "Structure posts with hooks, value, and clear CTAs."
    ),
    "connection_note": (
        "You are a professional networker on LinkedIn. Craft short, personalized connection "
        "notes (max 300 characters). Reference specific details from the recipient's profile. "
        "Be genuine, avoid salesy language. The goal is to build authentic connections."
    ),
    "sales_first_message": (
        "You are a B2B sales professional. Write a personalized first message that feels "
        "natural and relevant. Reference the recipient's role, company, or recent activity. "
        "Lead with value, not a pitch. Keep it concise (under 500 characters). "
        "Optimize for getting a positive reply."
    ),
    "followup": (
        "You are following up on a previous LinkedIn conversation. Be contextually aware. "
        "Reference previous exchanges. Provide additional value or a new angle. "
        "Gradually escalate toward a meeting/demo without being pushy. "
        "Adapt based on the recipient's previous responses and intent signals."
    ),
    "objection_handler": (
        "You are handling a sales objection on LinkedIn. Acknowledge the concern, reframe "
        "with empathy, and provide a compelling counter-point. Keep it conversational. "
        "The goal is to move the conversation forward positively."
    ),
    "intent_detection": (
        "Analyze the following LinkedIn message and classify the sender's intent into one of: "
        "interested, not_interested, objection, needs_followup, meeting_ready. "
        "Also provide a sentiment score from -1.0 (very negative) to 1.0 (very positive) "
        "and a conversion probability from 0.0 to 1.0. "
        "Respond ONLY in JSON: {\"intent\": \"...\", \"sentiment\": 0.0, \"probability\": 0.0, \"reasoning\": \"...\"}"
    ),
    "profile_analysis": (
        "Analyze this LinkedIn profile data and extract: key interests, potential pain points, "
        "communication style preference, best approach angle for B2B outreach, and any "
        "conversation hooks. Respond in JSON format."
    ),
}


class LLMService:
    """Wrapper around Ollama for all LLM operations."""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self.embedding_model = settings.OLLAMA_EMBEDDING_MODEL

    # ── Core generation ─────────────────────────────────
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        context: Optional[list[dict]] = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context:
            messages.extend(context)
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    # ── Embeddings ──────────────────────────────────────
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_embedding(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.embedding_model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json().get("embedding", [])

    # ── RAG: store & retrieve ───────────────────────────
    async def store_embedding(self, text: str, metadata: dict[str, Any] = None) -> str:
        embedding = await self.get_embedding(text)
        vec = np.array([embedding], dtype="float32")
        idx = _get_faiss_index(len(embedding))
        idx.add(vec)

        doc_id = hashlib.sha256(text.encode()).hexdigest()[:16]
        _vector_store[doc_id] = {
            "text": text,
            "metadata": metadata or {},
            "embedding": embedding,
        }
        return doc_id

    async def retrieve_similar(self, query: str, top_k: int = 5) -> list[dict]:
        if not _vector_store:
            return []

        query_embedding = await self.get_embedding(query)
        vec = np.array([query_embedding], dtype="float32")
        idx = _get_faiss_index(len(query_embedding))

        k = min(top_k, idx.ntotal)
        if k == 0:
            return []

        distances, indices = idx.search(vec, k)
        store_keys = list(_vector_store.keys())

        results = []
        for i, score in zip(indices[0], distances[0]):
            if 0 <= i < len(store_keys):
                doc = _vector_store[store_keys[i]]
                results.append({"text": doc["text"], "metadata": doc["metadata"], "score": float(score)})
        return results

    # ── High-level operations ───────────────────────────
    async def generate_post(
        self,
        topic: str,
        tone: str = "professional",
        audience: str = "general",
        previous_performance: Optional[dict] = None,
        hashtags: Optional[list[str]] = None,
    ) -> str:
        context_parts = [f"Topic: {topic}", f"Tone: {tone}", f"Target audience: {audience}"]
        if previous_performance:
            context_parts.append(f"Previous post performance: {json.dumps(previous_performance)}")
            context_parts.append("Improve upon the previous post based on performance data.")
        if hashtags:
            context_parts.append(f"Suggested hashtags: {', '.join(hashtags)}")

        prompt = "\n".join(context_parts) + "\n\nGenerate a LinkedIn post:"
        return await self.generate(prompt, system_prompt=SYSTEM_PROMPTS["post_generator"])

    async def generate_connection_note(self, profile_data: dict) -> str:
        prompt = f"Recipient profile:\n{json.dumps(profile_data, indent=2)}\n\nGenerate a personalized connection note (max 300 characters):"
        return await self.generate(prompt, system_prompt=SYSTEM_PROMPTS["connection_note"], max_tokens=100)

    async def generate_first_message(self, profile_data: dict, campaign_context: str = "") -> str:
        # RAG: retrieve relevant context
        rag_context = await self.retrieve_similar(json.dumps(profile_data), top_k=3)
        rag_text = "\n".join([r["text"] for r in rag_context]) if rag_context else "No prior context."

        prompt = (
            f"Recipient profile:\n{json.dumps(profile_data, indent=2)}\n"
            f"Campaign context: {campaign_context}\n"
            f"Relevant prior interactions:\n{rag_text}\n\n"
            "Generate a personalized first outreach message:"
        )
        return await self.generate(prompt, system_prompt=SYSTEM_PROMPTS["sales_first_message"])

    async def generate_followup(
        self,
        conversation_history: list[dict],
        profile_data: dict,
        followup_number: int,
        conversation_memory: Optional[dict] = None,
    ) -> str:
        memory_text = json.dumps(conversation_memory) if conversation_memory else "No memory."
        prompt = (
            f"Conversation history:\n{json.dumps(conversation_history, indent=2)}\n"
            f"Recipient profile: {json.dumps(profile_data)}\n"
            f"Conversation memory: {memory_text}\n"
            f"This is follow-up #{followup_number}.\n\n"
            "Generate the next follow-up message:"
        )
        return await self.generate(prompt, system_prompt=SYSTEM_PROMPTS["followup"])

    async def handle_objection(self, objection: str, conversation_history: list[dict], profile_data: dict) -> str:
        prompt = (
            f"Objection: {objection}\n"
            f"Conversation history:\n{json.dumps(conversation_history, indent=2)}\n"
            f"Recipient profile: {json.dumps(profile_data)}\n\n"
            "Generate a response to handle this objection:"
        )
        return await self.generate(prompt, system_prompt=SYSTEM_PROMPTS["objection_handler"])

    async def detect_intent(self, message: str, conversation_history: list[dict] = None) -> dict:
        history_text = json.dumps(conversation_history) if conversation_history else "[]"
        prompt = (
            f"Message to analyze: \"{message}\"\n"
            f"Conversation history: {history_text}\n\n"
            "Classify the intent:"
        )
        result = await self.generate(prompt, system_prompt=SYSTEM_PROMPTS["intent_detection"], temperature=0.3)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"intent": "needs_followup", "sentiment": 0.0, "probability": 0.0, "reasoning": result}

    async def analyze_profile(self, profile_data: dict) -> dict:
        prompt = f"LinkedIn profile data:\n{json.dumps(profile_data, indent=2)}\n\nAnalyze this profile:"
        result = await self.generate(prompt, system_prompt=SYSTEM_PROMPTS["profile_analysis"], temperature=0.3)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"raw_analysis": result}

    async def summarize_conversation(self, messages: list[dict]) -> str:
        prompt = (
            f"Conversation messages:\n{json.dumps(messages, indent=2)}\n\n"
            "Provide a concise summary of this conversation including: key topics discussed, "
            "recipient's interests and concerns, current intent, and recommended next action."
        )
        return await self.generate(prompt, temperature=0.3, max_tokens=512)


# Singleton
llm_service = LLMService()

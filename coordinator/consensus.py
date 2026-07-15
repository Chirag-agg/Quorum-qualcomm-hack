import re
from typing import List, Dict, Any
from .logger import event_logger

class ConsensusEngine:
    @staticmethod
    def normalize_answer(answer: str) -> str:
        """Simple normalization: strip whitespace and lowercase."""
        return re.sub(r'\s+', ' ', answer.strip().lower())

    @staticmethod
    def resolve(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        candidates: List of dicts like {"device": "phone", "answer": "42", "quorum_score": 0.85}
        """
        if not candidates:
            return {"answer": None, "confidence": 0.0, "winner": None}

        counts = {}
        highest_score_for_ans = {}
        
        for cand in candidates:
            ans = ConsensusEngine.normalize_answer(cand["answer"])
            score = cand.get("quorum_score", 0.0)
            
            counts[ans] = counts.get(ans, 0) + 1
            if ans not in highest_score_for_ans or score > highest_score_for_ans[ans]["score"]:
                highest_score_for_ans[ans] = {"score": score, "device": cand["device"], "original_answer": cand["answer"]}

        # Find the max vote count
        max_votes = max(counts.values())
        tied_answers = [ans for ans, count in counts.items() if count == max_votes]

        # Resolve ties by picking the answer with the highest quorum score among the tied answers
        best_ans = None
        best_score = -1.0
        
        for ans in tied_answers:
            if highest_score_for_ans[ans]["score"] > best_score:
                best_score = highest_score_for_ans[ans]["score"]
                best_ans = ans

        winning_record = highest_score_for_ans[best_ans]
        
        event_logger.log("Consensus Reached", {
            "winning_answer": winning_record["original_answer"],
            "votes": max_votes,
            "quorum_score": best_score,
            "winning_device": winning_record["device"]
        })
        
        return {
            "answer": winning_record["original_answer"],
            "quorum_score": best_score,
            "winner": winning_record["device"],
            "votes": max_votes
        }

consensus_engine = ConsensusEngine()

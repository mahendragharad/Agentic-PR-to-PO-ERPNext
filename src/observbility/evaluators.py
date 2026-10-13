import logging
import time
from typing import Any, Dict, List
from langfuse import get_client

logger = logging.getLogger("mcp_agent_evaluator")
langfuse_client = get_client()

class ProductionAgentEvaluator:
    @staticmethod
    def evaluate_and_score_trace(
        trace_id: str, 
        user_query: str, 
        final_state: Dict[str, Any], 
        start_time: float
    ) -> Dict[str, float]:
        scores = {}
        # Protect against empty states safely
        messages: List[Any] = final_state.get("messages", []) if final_state else []
        
        # 1. Latency SLA
        execution_latency = time.time() - start_time
        scores["execution_latency_sla"] = 1.0 if execution_latency <= 15.0 else max(0.0, 1.0 - (execution_latency - 15.0) / 30.0)
        
        # 2. Tool Density Budget 
        tool_calls = [msg for msg in messages if getattr(msg, "type", "") == "tool"]
        tool_count = len(tool_calls)
        scores["tool_budget_compliance"] = 1.0 if tool_count <= 5 else max(0.0, 1.0 - (tool_count - 5) / 5.0)
        
        # 3. Self-Healing Trackers
        retry_counter: Dict[str, Any] = final_state.get("retry_counter", {})
        total_retries = sum(retry_counter.values()) if isinstance(retry_counter, dict) else 0
        had_error = final_state.get("last_error_context") is not None if final_state else False
        
        if had_error and total_retries > 0:
            scores["self_healing_efficiency"] = max(0.1, 1.0 - (total_retries / 3.0))
        elif not had_error and total_retries == 0:
            scores["self_healing_efficiency"] = 1.0
        else:
            scores["self_healing_efficiency"] = 0.0

        # 4. Content Output Completeness
        final_text = messages[-1].content if messages else ""
        scores["response_completeness"] = 1.0 if (isinstance(final_text, str) and len(final_text.strip()) > 5) else 0.0

        try:
            for metric_name, score_value in scores.items():
                # Post score direct matching route allocation
                langfuse_client.create_score(
                    trace_id=trace_id,
                    name=metric_name,
                    value=float(score_value),
                    comment=f"Automated eval: tool_count={tool_count}, retries={total_retries}"
                )
            # Push out of memory blocks immediately
            langfuse_client.flush()
            logger.info(f"✅ Telemetry evaluation matrices posted successfully for trace: {trace_id}")
        except Exception as err:
            logger.error(f"Failed posting evaluation matrix data to Langfuse: {str(err)}")
            
        return scores

# app/services/modification_service.py
from typing import Dict, List, Any
import google.generativeai as genai
import json
import os
import logging
import re

logger = logging.getLogger(__name__)

class DiagramModifier:
    """Service for intelligently modifying existing diagrams using AI"""
    
    def __init__(self):
        # Initialize Gemini
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        self.modification_prompt_template = """
You are an expert system architect modifying architecture diagrams.

CONVERSATION HISTORY:
{conversation_history}

CURRENT DIAGRAM (JSON):
{current_diagram}

USER REQUEST: "{modification_request}"

MODIFICATION RULES:
1. ADD: If request says "add X", create a new node for X
2. REMOVE: If request says "remove X" or "delete X", DELETE all nodes containing X in their label
3. UPDATE: If request says "change X to Y" or "make X use Y", UPDATE existing node X
4. CONNECT: If request says "connect X to Y", add an edge between them
5. If a component already exists, UPDATE it instead of creating duplicate

CONTEXT INSTRUCTIONS:
- Use the conversation history to understand previous versions and maintain consistency
- Ensure modifications align with the architectural context from past versions
- Avoid duplicating components unnecessarily based on history

CRITICAL REQUIREMENTS:
- Return ONLY valid JSON in this EXACT format: {{"nodes": [...], "edges": [...]}}
- Each node MUST have: {{"id": "node_X", "type": "custom", "data": {{"label": "...", "type": "..."}}, "position": {{"x": 100, "y": 100}}}}
- Each edge MUST have: {{"id": "edge_X", "source": "node_X", "target": "node_Y", "type": "smoothstep", "label": "uses", "animated": false}}
- When REMOVING nodes, also remove all edges connected to those nodes
- Preserve node IDs for existing nodes that aren't being removed
- DO NOT add any explanation, ONLY return the JSON

Return the complete modified diagram JSON now:
"""
    
    def apply_modification(
        self, 
        current_diagram: Dict, 
        modification_request: str,
        conversation_history: List[Dict] = None
    ) -> Dict:
        """
        Apply modifications to diagram using AI with full context
        """
        try:
            logger.info(f"🔧 Starting modification: '{modification_request}'")
            logger.info(f"📊 Current diagram has {len(current_diagram.get('nodes', []))} nodes")
            
            # Prepare conversation history for prompt
            conversation_history_str = json.dumps(conversation_history, indent=2) if conversation_history else "[]"
            
            # Construct prompt with history
            prompt = self.modification_prompt_template.format(
                conversation_history=conversation_history_str,
                current_diagram=json.dumps(current_diagram, indent=2),
                modification_request=modification_request
            )
            
            logger.info(f"🤖 Sending to Gemini AI...")
            
            # Generate with AI
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,  # Low temperature for consistent output
                )
            )
            response_text = response.text.strip()
            
            logger.info(f"📨 AI Response length: {len(response_text)} chars")
            logger.debug(f"AI Response preview: {response_text[:500]}...")
            
            # Extract JSON
            modified_diagram = self._extract_json_from_response(response_text)
            
            if not modified_diagram:
                logger.error("❌ Failed to extract valid JSON from AI response")
                logger.error(f"Response was: {response_text}")
                return current_diagram
            
            # Validate structure
            if not self._validate_diagram_structure(modified_diagram):
                logger.error("❌ Invalid diagram structure from AI")
                return current_diagram
            
            logger.info(f"✅ Successfully modified! New diagram has {len(modified_diagram.get('nodes', []))} nodes")
            return modified_diagram
            
        except Exception as e:
            logger.error(f"❌ Modification error: {str(e)}", exc_info=True)
            return current_diagram
    
    def _extract_json_from_response(self, response_text: str) -> Dict:
        """Extract JSON from AI response (handles markdown code blocks)"""
        try:
            # Try direct parse
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code block
        patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{.*\})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response_text, re.DOTALL)
            if match:
                try:
                    json_str = match.group(1).strip()
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue
        
        logger.error("Failed to extract JSON from response")
        return None
    
    def _validate_diagram_structure(self, diagram: Dict) -> bool:
        """Validate diagram has required structure"""
        if not isinstance(diagram, dict):
            logger.error("Diagram is not a dict")
            return False
        
        if "nodes" not in diagram or "edges" not in diagram:
            logger.error("Missing 'nodes' or 'edges' key")
            return False
        
        if not isinstance(diagram["nodes"], list):
            logger.error("'nodes' is not a list")
            return False
        
        if not isinstance(diagram["edges"], list):
            logger.error("'edges' is not a list")
            return False
        
        # Validate each node has required fields
        for i, node in enumerate(diagram["nodes"]):
            if not isinstance(node, dict):
                logger.error(f"Node {i} is not a dict")
                return False
            
            if "id" not in node:
                logger.error(f"Node {i} missing 'id'")
                return False
            
            if "data" not in node or not isinstance(node["data"], dict):
                logger.error(f"Node {i} missing or invalid 'data'")
                return False
            
            if "label" not in node["data"]:
                logger.error(f"Node {i} missing 'label' in data")
                return False
            
            if "position" not in node:
                logger.error(f"Node {i} missing 'position'")
                return False
        
        logger.info(f"✅ Validation passed: {len(diagram['nodes'])} nodes, {len(diagram['edges'])} edges")
        return True
    
    def get_modification_summary(self, old_diagram: Dict, new_diagram: Dict) -> Dict:
        """Generate summary of what changed"""
        old_nodes = old_diagram.get("nodes", [])
        new_nodes = new_diagram.get("nodes", [])
        old_edges = old_diagram.get("edges", [])
        new_edges = new_diagram.get("edges", [])
        
        # Track changes
        old_node_ids = {n["id"] for n in old_nodes}
        new_node_ids = {n["id"] for n in new_nodes}
        
        old_node_labels = {n["id"]: n.get("data", {}).get("label", "") for n in old_nodes}
        new_node_labels = {n["id"]: n.get("data", {}).get("label", "") for n in new_nodes}
        
        nodes_added = new_node_ids - old_node_ids
        nodes_removed = old_node_ids - new_node_ids
        
        # Check for updated nodes (same ID, different label)
        nodes_updated = []
        for node_id in old_node_ids & new_node_ids:
            if old_node_labels.get(node_id) != new_node_labels.get(node_id):
                nodes_updated.append({
                    "id": node_id,
                    "old": old_node_labels.get(node_id),
                    "new": new_node_labels.get(node_id)
                })
        
        removed_details = [
            {"id": node_id, "label": old_node_labels.get(node_id)}
            for node_id in nodes_removed
        ]
        
        added_details = [
            {"id": node_id, "label": new_node_labels.get(node_id)}
            for node_id in nodes_added
        ]
        
        summary = {
            "nodes_added": len(nodes_added),
            "nodes_removed": len(nodes_removed),
            "nodes_updated": len(nodes_updated),
            "updated_details": nodes_updated,
            "removed_details": removed_details,
            "added_details": added_details,
            "edges_added": max(0, len(new_edges) - len(old_edges)),
            "edges_removed": max(0, len(old_edges) - len(new_edges)),
            "total_nodes": len(new_nodes),
            "total_edges": len(new_edges)
        }
        
        logger.info(f"📊 Modification Summary:")
        logger.info(f"   ➕ Added: {summary['nodes_added']} nodes")
        logger.info(f"   ➖ Removed: {summary['nodes_removed']} nodes")
        logger.info(f"   ✏️ Updated: {summary['nodes_updated']} nodes")
        
        if removed_details:
            logger.info(f"   Removed components:")
            for detail in removed_details:
                logger.info(f"      - {detail['label']}")
        
        return summary
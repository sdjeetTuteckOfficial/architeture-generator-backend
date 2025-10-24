# app/services/modification_service.py
from typing import Dict, List, Any
import re


class DiagramModifier:
    """Service for intelligently modifying existing diagrams"""
    
    def __init__(self):
        self.modification_keywords = {
            "add": ["add", "include", "insert", "new", "create"],
            "remove": ["remove", "delete", "eliminate", "drop", "exclude"],
            "update": ["change", "modify", "update", "replace", "rename"],
            "connect": ["connect", "link", "integrate", "join", "attach"],
            "disconnect": ["disconnect", "unlink", "separate", "detach"]
        }
    
    def detect_modification_type(self, request: str) -> str:
        """Detect what type of modification is being requested"""
        request_lower = request.lower()
        
        for mod_type, keywords in self.modification_keywords.items():
            if any(keyword in request_lower for keyword in keywords):
                return mod_type
        
        return "unknown"
    
    def extract_component_names(self, text: str) -> List[str]:
        """Extract component/service names from text"""
        # Common patterns for component names
        patterns = [
            r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)*)\b',  # CamelCase
            r'"([^"]+)"',  # Quoted text
            r"'([^']+)'",  # Single quoted
        ]
        
        components = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            components.extend(matches)
        
        return list(set(components))
    
    def add_components(self, diagram: Dict, components: List[str]) -> Dict:
        """Add new components to diagram"""
        nodes = diagram.get("nodes", [])
        edges = diagram.get("edges", [])
        
        existing_labels = {node.get("data", {}).get("label", "").lower() for node in nodes}
        
        for comp in components:
            if comp.lower() not in existing_labels:
                node_id = f"node_{len(nodes) + 1}"
                nodes.append({
                    "id": node_id,
                    "type": "custom",
                    "data": {
                        "label": comp,
                        "type": self._guess_component_type(comp)
                    },
                    "position": {
                        "x": 100 + (len(nodes) % 3) * 250,
                        "y": 100 + (len(nodes) // 3) * 200
                    }
                })
        
        return {"nodes": nodes, "edges": edges}
    
    def remove_components(self, diagram: Dict, components: List[str]) -> Dict:
        """Remove components from diagram"""
        nodes = diagram.get("nodes", [])
        edges = diagram.get("edges", [])
        
        # Find nodes to remove
        nodes_to_remove = []
        for comp in components:
            for node in nodes:
                label = node.get("data", {}).get("label", "").lower()
                if comp.lower() in label:
                    nodes_to_remove.append(node["id"])
        
        # Remove nodes
        nodes = [n for n in nodes if n["id"] not in nodes_to_remove]
        
        # Remove associated edges
        node_ids = [n["id"] for n in nodes]
        edges = [
            e for e in edges 
            if e.get("source") in node_ids and e.get("target") in node_ids
        ]
        
        return {"nodes": nodes, "edges": edges}
    
    def connect_components(self, diagram: Dict, source: str, target: str, relationship: str = "uses") -> Dict:
        """Create connection between components"""
        nodes = diagram.get("nodes", [])
        edges = diagram.get("edges", [])
        
        # Find source and target nodes
        source_node = None
        target_node = None
        
        for node in nodes:
            label = node.get("data", {}).get("label", "").lower()
            if source.lower() in label:
                source_node = node["id"]
            if target.lower() in label:
                target_node = node["id"]
        
        # Add edge if both nodes found
        if source_node and target_node:
            edge_id = f"edge_{len(edges) + 1}"
            edges.append({
                "id": edge_id,
                "source": source_node,
                "target": target_node,
                "type": "smoothstep",
                "label": relationship,
                "animated": False
            })
        
        return {"nodes": nodes, "edges": edges}
    
    def update_component(self, diagram: Dict, old_name: str, new_name: str) -> Dict:
        """Update/rename a component"""
        nodes = diagram.get("nodes", [])
        edges = diagram.get("edges", [])
        
        for node in nodes:
            label = node.get("data", {}).get("label", "")
            if old_name.lower() in label.lower():
                node["data"]["label"] = new_name
                break
        
        return {"nodes": nodes, "edges": edges}
    
    def _guess_component_type(self, name: str) -> str:
        """Guess component type from name"""
        name_lower = name.lower()
        
        if "db" in name_lower or "database" in name_lower:
            return "database"
        elif "api" in name_lower:
            return "api"
        elif "service" in name_lower:
            return "service"
        elif "queue" in name_lower:
            return "queue"
        elif "cache" in name_lower:
            return "cache"
        else:
            return "service"
    
    def apply_modification(self, diagram: Dict, request: str) -> Dict:
        """Main method to apply modifications based on natural language request"""
        mod_type = self.detect_modification_type(request)
        components = self.extract_component_names(request)
        
        if mod_type == "add":
            return self.add_components(diagram, components)
        
        elif mod_type == "remove":
            return self.remove_components(diagram, components)
        
        elif mod_type == "update" and len(components) >= 2:
            return self.update_component(diagram, components[0], components[1])
        
        elif mod_type == "connect" and len(components) >= 2:
            relationship = "uses"
            if "via" in request.lower():
                # Extract relationship type
                via_match = re.search(r'via\s+(\w+)', request.lower())
                if via_match:
                    relationship = via_match.group(1)
            
            return self.connect_components(diagram, components[0], components[1], relationship)
        
        elif mod_type == "disconnect" and len(components) >= 2:
            return self.disconnect_components(diagram, components[0], components[1])
        
        else:
            # If we can't determine type, try to add as new components
            if components:
                return self.add_components(diagram, components)
        
        return diagram
    
    def disconnect_components(self, diagram: Dict, source: str, target: str) -> Dict:
        """Remove connection between components"""
        nodes = diagram.get("nodes", [])
        edges = diagram.get("edges", [])
        
        # Find source and target nodes
        source_node = None
        target_node = None
        
        for node in nodes:
            label = node.get("data", {}).get("label", "").lower()
            if source.lower() in label:
                source_node = node["id"]
            if target.lower() in label:
                target_node = node["id"]
        
        # Remove edges between these nodes
        if source_node and target_node:
            edges = [
                e for e in edges 
                if not ((e.get("source") == source_node and e.get("target") == target_node) or
                       (e.get("source") == target_node and e.get("target") == source_node))
            ]
        
        return {"nodes": nodes, "edges": edges}
    
    def get_modification_summary(self, old_diagram: Dict, new_diagram: Dict) -> Dict:
        """Generate summary of what changed"""
        old_nodes = len(old_diagram.get("nodes", []))
        new_nodes = len(new_diagram.get("nodes", []))
        old_edges = len(old_diagram.get("edges", []))
        new_edges = len(new_diagram.get("edges", []))
        
        return {
            "nodes_added": max(0, new_nodes - old_nodes),
            "nodes_removed": max(0, old_nodes - new_nodes),
            "edges_added": max(0, new_edges - old_edges),
            "edges_removed": max(0, old_edges - new_edges),
            "total_nodes": new_nodes,
            "total_edges": new_edges
        }
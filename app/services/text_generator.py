import json
import re
from typing import Dict, List, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
import os

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.7, max_tokens=4000)

class TextArchitectureGenerator:
    """Generate detailed text-based architecture documents"""
    
    def generate_detailed_architecture(self, description: str, context: Dict[str, Any], 
                                     user_responses: Dict[str, str]) -> Dict[str, Any]:
        """Generate comprehensive architecture document"""
        
        domain = context.get("project_domain", "software system")
        
        arch_prompt = f"""
        You are a senior software architect. Create a comprehensive architecture document for this {domain} project:
        
        PROJECT DESCRIPTION: {description}
        CONTEXT: {json.dumps(context, indent=2)}
        ADDITIONAL REQUIREMENTS: {json.dumps(user_responses, indent=2)}
        
        Generate a detailed architecture document with these sections:
        
        1. **Executive Summary**: Project overview and key architectural decisions
        2. **System Architecture**: High-level system design and component interaction
        3. **Technology Stack**: Recommended technologies with justifications
        4. **Service Architecture**: Detailed breakdown of microservices/components
        5. **Data Architecture**: Database design, data flow, and storage strategy
        6. **Security Architecture**: Authentication, authorization, and security measures
        7. **Scalability Strategy**: Horizontal/vertical scaling approaches
        8. **Integration Architecture**: APIs, message queues, external services
        9. **Deployment Strategy**: Infrastructure, CI/CD, and deployment patterns
        10. **Monitoring & Observability**: Logging, metrics, and monitoring strategy
        11. **Performance Considerations**: Caching, optimization, and performance targets
        12. **Risk Assessment**: Technical risks and mitigation strategies
        
        Make it specific to {domain}, technically detailed, and actionable.
        Include specific technology recommendations with reasoning.
        """
        
        try:
            response = llm.invoke([HumanMessage(content=arch_prompt)])
            
            rec_prompt = f"""
            Based on this architecture document, extract 5-8 key technical recommendations as a JSON array:
            
            {response.content[:2000]}...
            
            Return: ["recommendation1", "recommendation2", ...]
            """
            
            rec_response = llm.invoke([HumanMessage(content=rec_prompt)])
            json_match = re.search(r'\[.*\]', rec_response.content, re.DOTALL)
            recommendations = json.loads(json_match.group()) if json_match else []
            
            return {
                "architecture": response.content,
                "recommendations": recommendations
            }
        except Exception as e:
            print(f"Text architecture error: {e}")
            return {
                "architecture": f"Error generating architecture document: {str(e)}",
                "recommendations": []
            }
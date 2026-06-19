import requests
import os
from typing import List, Dict, Any, Optional
from chatbot.llm_models.llm_script import handle_bedrock_model

DATABASE_INTERFACE_BEARER_TOKEN = os.getenv('DATABASE_INTERFACE_BEARER_TOKEN')
base_url = os.getenv('VECTOR_DB_BASE_URL')

def query_database(query_prompt: str, priority_filter: str, limit: int):
    """
    Query vector database to retrieve chunk with user's input questions.
    """
    url = f"{base_url}/api/documents/search"
    print("URL: ", url)
    headers = {
        "Content-Type": "application/json",
        "accept": "application/json",
    }
    data = {
        "query": query_prompt,
        "top_k": limit,
    }
    # if priority_filter:
    #     data["priority_filter"] = priority_filter
    print("DATA: ", data)
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        result = response.json()
        print("response: ", result)
        # process the result
        return result
    else:
        print(f"Error: {response.status_code} : {response.content}")


def query_text_search(query: str, priority: str = "P1", limit: int = 10):
    """
    Query vector database using text-search API endpoint.
    """
    url = f"{base_url}/api/documents/text-search"
    print(f"[query_text_search] URL: {url}")
    
    headers = {
        "Content-Type": "application/json",
        "accept": "application/json",
    }
    
    payload = {
        "query": query,
        "priority": priority,
        "limit": limit
    }
    
    print(f"[query_text_search] Request Payload: {payload}")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"[query_text_search] Success: Retrieved {result.get('total_results', 0)} results")
            return result
        else:
            error_msg = f"Error: {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail}"
            except:
                error_msg += f" - {response.text}"
            
            print(f"[query_text_search] {error_msg}")
            return {
                "error": True,
                "status_code": response.status_code,
                "message": error_msg,
                "query": query,
                "total_results": 0,
                "results": []
            }
    
    except requests.exceptions.Timeout:
        error_msg = "Request timeout - Vector database took too long to respond"
        print(f"[query_text_search] {error_msg}")
        return {
            "error": True,
            "status_code": 504,
            "message": error_msg,
            "query": query,
            "total_results": 0,
            "results": []
        }
    
    except requests.exceptions.ConnectionError:
        error_msg = "Connection error - Unable to reach vector database"
        print(f"[query_text_search] {error_msg}")
        return {
            "error": True,
            "status_code": 503,
            "message": error_msg,
            "query": query,
            "total_results": 0,
            "results": []
        }
    
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"[query_text_search] {error_msg}")
        return {
            "error": True,
            "status_code": 500,
            "message": error_msg,
            "query": query,
            "total_results": 0,
            "results": []
        }


def query_database_with_metadata(
    query: str = None,
    top_k: int = 20,
    filter_score: int = 0,
    detail_filter_score: Optional[Dict[str, Any]] = None,
    categories: List[str] = None,
    organizations: List[str] = None,
    resource_type: List[str] = None,
    file_type: List[str] = None
):
    """
    Query vector database with metadata filters for media search v2.
    """
    url = f"{base_url}/api/documents/search"
    print(f"[query_database_with_metadata] URL: {url}")
    
    headers = {
        "Content-Type": "application/json",
        "accept": "application/json",
    }
    
    # Build request payload
    data = {
        "top_k": top_k,
        "filter_score": filter_score,
        "detail_filter_score": detail_filter_score
    }
    
    # Add query only if provided
    if query:
        data["query"] = query
    
    # Add optional filters if provided
    if categories:
        data["categories"] = categories
    if organizations:
        data["organizations"] = organizations
    if resource_type:
        data["resource_type"] = resource_type
    if file_type:
        data["file_type"] = file_type
    
    print(f"[query_database_with_metadata] Request Data: {data}")
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"[query_database_with_metadata] Success: Retrieved {len(result.get('results', []))} results")
            return result
        else:
            error_msg = f"Error: {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail}"
            except:
                error_msg += f" - {response.text}"
            
            print(f"[query_database_with_metadata] {error_msg}")
            return {
                "error": True,
                "status_code": response.status_code,
                "message": error_msg,
                "query": query,
                "total_results": 0,
                "top_k": top_k,
                "results": []
            }
    
    except requests.exceptions.Timeout:
        error_msg = "Request timeout - Vector database took too long to respond"
        print(f"[query_database_with_metadata] {error_msg}")
        return {
            "error": True,
            "status_code": 504,
            "message": error_msg,
            "query": query,
            "total_results": 0,
            "top_k": top_k,
            "results": []
        }
    
    except requests.exceptions.ConnectionError:
        error_msg = "Connection error - Unable to reach vector database"
        print(f"[query_database_with_metadata] {error_msg}")
        return {
            "error": True,
            "status_code": 503,
            "message": error_msg,
            "query": query,
            "total_results": 0,
            "top_k": top_k,
            "results": []
        }
    
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"[query_database_with_metadata] {error_msg}")
        return {
            "error": True,
            "status_code": 500,
            "message": error_msg,
            "query": query,
            "total_results": 0,
            "top_k": top_k,
            "results": []
        }


def apply_prompt_template(question: str) -> str:
    """
        A helper function that applies additional template on user's question.
        Prompt engineering could be done here to improve the result. Here I will just use a minimal example.
    """
    prompt = f"""
        Based on the above data (if applicable) please answer to following question/greeting: 
        {question}

        REMEMBER STRICTLY DO NOT PROVIDE ANY INFORMATION WHICH IS OUTSIDE OF CONTEXT AVAILABLE TO YOU.
    """
    return prompt


def call_bedrock_api(prompt, messages, temperature, company_bot, chunks: List[str]):
    """
    Call chatgpt api with user's question and retrieved chunks.
    """
    text_to_add = " Use the following chunks along with the other information provided to generate the output:\n"
    prompt[0]['text'] += text_to_add + ''.join(
        map(lambda chunk: f"\n{chunk}", chunks)
    )
    print(messages)

    response = handle_bedrock_model(
        system_prompt=prompt, messages=messages, max_token=2048,
        temperature=temperature, company_bot=company_bot
    )

    return response


def ask(messages, user_question, temperature, priority_filter, top_k, prompt, filter_score, company_bot):
    """
    Handle user's questions.
    """
    chunks_response = query_database(query_prompt=user_question, priority_filter=priority_filter, limit=top_k)
    print("chunks_response", chunks_response)
    chunks = []
    if chunks_response and chunks_response["relevant_texts"]:
        for result in chunks_response["relevant_texts"]:
            print(f"relevance_score: {result['relevance_score']} filter_score: {filter_score}")
            if ("qdrant_recommendation_text" in result and result["qdrant_recommendation_text"] is not None
                and len(result["qdrant_recommendation_text"]) > 20 and result["relevance_score"] >= filter_score
            ):
                chunks.append(result["qdrant_recommendation_text"])

            elif ("translated_text" in result and result["translated_text"] is not None
                  and len(result["translated_text"]) > 20):
                chunks.append(result["translated_text"])
    print("\nCHUNKS: ", chunks)
    chunks = []
    print("\nChunk Response: ", chunks_response)
    response = call_bedrock_api(
        prompt=prompt, messages=messages, temperature=temperature, chunks=chunks, company_bot=company_bot
    )
    return response, chunks, chunks_response

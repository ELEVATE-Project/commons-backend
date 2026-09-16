

def get_end_story_tools():
    tool = {
        "toolConfig": {
            "tools": [
                {
                    "toolSpec": {
                        "name": "get_story_output",
                        "description": "Generate a detailed narrative output in a valid JSON format containing specific fields.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "title": {
                                        "type": "string",
                                        "description": "Title of the story"
                                    },
                                    "objective": {
                                        "type": "string",
                                        "description": "Objective of the micro improvement"
                                    },
                                    "action_steps": {
                                        "type": "string",
                                        "description": "5 Action steps taken by the user to implement the micro improvement"
                                    },
                                    "impact": {
                                        "type": "string",
                                        "description": "Impact created from this micro improvement"
                                    },
                                    "micro_improvement": {
                                        "type": "string",
                                        "description": "Why is this micro-improvement important"
                                    },
                                    "resource_name": {
                                        "type": "string",
                                        "description": "Learning resources name that you want the stakeholders to see while doing the project"
                                    },
                                    "resource_link": {
                                        "type": "string",
                                        "description": "Learning resources link that you want the stakeholders to see while doing the project"
                                    },
                                    "duration": {
                                        "type": "string",
                                        "description": "Total time span of the project, from start to end"
                                    },
                                    "keywords": {
                                        "type": "string",
                                        "description": "Keywords improve search ability, tag this Improvement project with appropriate keywords"
                                    },
                                    "status": {
                                        "type": "string",
                                        "description": "The current state of the project, such as 'STARTED,' 'inPROGRESS,' or 'SUBMITTED'"
                                    },
                                    "project_start_date": {
                                        "type": "string",
                                        "description": "Starting date of the project if any"
                                    },
                                    "project_end_date": {
                                        "type": "string",
                                        "description": "Completion date of project if any"
                                    },
                                    "problem_statement": {
                                        "type": "string",
                                        "description": "The challenge faced by the user and what they wanted to solve"
                                    }
                                },
                                "required": ["title", "objective", "action_steps", "impact", "micro_improvement",
                                             "duration", "status", "problem_statement"]
                            }
                        }
                    }
                }
            ]
        }
    }

    return tool


def get_story_content_tools():
    tool = {
        "toolConfig": {
            "tools": [
                {
                    "toolSpec": {
                        "name": "get_story_output",
                        "description": "Generate a detailed narrative output in a valid JSON format containing specific fields.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "content": {
                                        "type": "string",
                                        "description": "NARRATIVE. MAKE SURE THE NARRATIVE GENERATED IS BETWEEN 500-600 WORDS"
                                    },
                                    "blurb": {
                                        "type": "string",
                                        "description": "first-person summary (2–3 sentences) from the user’s perspective"
                                    }
                                },
                                "required": ["content", "blurb"]
                            }
                        }
                    }
                }
            ]
        }
    }

    return tool

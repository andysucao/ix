import json
from django.core.management.base import BaseCommand

from ix.agents.models import Agent
from ix.chains.models import ChainNode, Chain


CREATE_FILE_LIST = """
You are a python coder. You are planning code edits for user requests. Respond with
a function call to create files for the user request.

{artifacts}

INSTRUCTIONS:
    - only include files that you will generate content for.
    - description should contain all details required to generate the file.
    - do not split new files into multiple actions.
    - do not include files that are generated by another process or command.
    - if editing an artifact, use the same identifier as the original artifact.
    - identifier is the filename including file extension.
"""


FILE_LIST_FUNCTION = {
    "class_path": "ix.chains.functions.FunctionSchema",
    "name": "create_action_list",
    "config": {
        "name": "create_file_list",
        "description": "creates a list of files to generate for users request",
        "parameters": json.dumps(
            {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["filename", "description"],
                        },
                    },
                },
            },
            indent=4,
        ),
    },
}


GENERATE_CODE = """
You are a python coder. You will writes files for the user request.

{artifacts}

FILE_LIST:
{file_list}

GENERATED FILES:
{file_contents}

FILE_META:
{file_meta}

INSTRUCTIONS:
    - respond with a function call
    - write the file described by the FILE_META
"""


CREATE_CODE_ARTIFACTS = {
    "class_path": "ix.chains.llm_chain.LLMChain",
    "config": {
        "verbose": True,
        "output_key": "file_list",
        "llm": {
            "class_path": "langchain_community.chat_models.ChatOpenAI",
            "config": {
                "model_name": "gpt-4-0613",
                "request_timeout": 240,
                "temperature": 0.2,
                "verbose": True,
                "max_tokens": 2000,
            },
        },
        "prompt": {
            "class_path": "ix.runnable.prompt.ChatPrompt",
            "config": {
                "messages": [
                    {
                        "role": "system",
                        "template": CREATE_FILE_LIST,
                        "input_variables": ["artifacts"],
                    },
                    {
                        "role": "user",
                        "template": "{user_input}",
                        "input_variables": ["user_input"],
                    },
                ],
            },
        },
        "functions": FILE_LIST_FUNCTION,
        "function_call": "create_file_list",
        "output_parser": {
            "class_path": "ix.chains.functions.OpenAIFunctionParser",
            "config": {
                "parse_json": True,
            },
        },
    },
}


SAVE_ARTIFACT_LIST = {
    "class_path": "ix.chains.artifacts.SaveArtifact",
    "config": {
        "artifact_key": "file_list",
        "artifact_name": "file_list",
        "artifact_description": "list of files that will be generated",
        "artifact_type": "file_list",
        "artifact_storage": "write_file",
        "content_key": "file_list.arguments.files",  # TODO: update
        "output_key": "file_list_artifact",
    },
}


GENERATE_FILE_ACTION_FUNCTION = {
    "class_path": "ix.chains.functions.FunctionSchema",
    "name": "file_action",
    "config": {
        "name": "create_file",
        "description": "creates a file. Use whenever you need to write a file..",
        "parameters": json.dumps(
            {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "description": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "description", "content"],
            },
            indent=4,
        ),
    },
}


GENERATE_FILE = {
    "class_path": "ix.chains.llm_chain.LLMChain",
    "config": {
        "verbose": True,
        "output_key": "file",
        "llm": {
            "class_path": "langchain_community.chat_models.ChatOpenAI",
            "config": {
                "model_name": "gpt-4-0613",
                "request_timeout": 240,
                "temperature": 0.2,
                "verbose": True,
                "max_tokens": 4000,
            },
        },
        "prompt": {
            "class_path": "langchain.prompts.chat.ChatPromptTemplate",
            "config": {
                "messages": [
                    {
                        "role": "system",
                        "template": GENERATE_CODE,
                        "input_variables": [
                            "file_meta",
                            "artifacts",
                            "file_contents",
                            "file_list",
                        ],
                    },
                    {
                        "role": "user",
                        "template": "file artifact list was generated from this input:\n {user_input}",
                        "input_variables": ["user_input"],
                    },
                ],
            },
        },
        "memory": {
            "class_path": "ix.memory.artifacts.ArtifactMemory",
            "config": {
                "input_key": "files",
                "memory_key": "file_contents",
            },
        },
        "functions": GENERATE_FILE_ACTION_FUNCTION,
        "function_call": "create_file",
        "output_parser": {
            "class_path": "ix.chains.functions.OpenAIFunctionParser",
            "config": {
                "parse_json": True,
            },
        },
    },
}


SAVE_FILE_ARTIFACT = {
    "class_path": "ix.chains.artifacts.SaveArtifact",
    "config": {
        "artifact_from_key": "file_meta",
        "artifact_type": "file",
        "artifact_storage": "write_to_file",
        "artifact_storage_id_key": "filename",
        "content_key": "file",
        "content_path": "file.arguments.content",
        "output_key": "file_artifact",
    },
}


GENERATE_FILES_MAP = {
    "name": "generate files",
    "description": "Generates files for each artifact in the input list",
    "class_path": "ix.chains.routing.MapSubchain",
    "config": {
        "input_variables": ["file_list", "artifacts", "user_input"],
        "map_input": "file_list.arguments.files",
        "map_input_to": "file_meta",
        "output_key": "files",
        "chains": [
            GENERATE_FILE,
            SAVE_FILE_ARTIFACT,
        ],
    },
}


CODER_SEQUENCE = {
    "name": "create files",
    "description": "Write new files containing code",
    "class_path": "langchain.chains.SequentialChain",
    "hidden": False,
    "config": {
        "input_variables": ["user_input"],
        "memory": {
            "class_path": "ix.memory.artifacts.ArtifactMemory",
            "config": {
                "memory_key": "artifacts",
            },
        },
        "chains": [
            CREATE_CODE_ARTIFACTS,
            SAVE_ARTIFACT_LIST,
            GENERATE_FILES_MAP,
        ],
    },
}


CODER_V2_CHAIN = "b7d8f662-12f6-4525-b07b-c9ea7c10010c"
CODER_V2_AGENT = "b7d8f662-12f6-4525-b07b-c9ea7c10010a"


class Command(BaseCommand):
    help = "Generates planner v4 chain"

    def handle(self, *args, **options):
        chain, is_new = Chain.objects.get_or_create(
            pk=CODER_V2_CHAIN,
            defaults=dict(
                name="Coder chain v2",
                description="Chain used to generate code files",
            ),
        )

        # clear old nodes
        chain.clear_chain()
        ChainNode.objects.create_from_config(
            chain=chain, root=True, config=CODER_SEQUENCE
        )

        Agent.objects.get_or_create(
            id=CODER_V2_AGENT,
            defaults=dict(
                name="Coder v2",
                alias="code",
                purpose="To generate code for a user request. May generate multiple files",
                chain=chain,
                config={},
            ),
        )

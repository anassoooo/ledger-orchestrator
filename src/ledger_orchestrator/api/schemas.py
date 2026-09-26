"""Validated request bodies for the local API."""

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    years:list[int]=Field(default_factory=lambda:[2023,2024,2025],min_length=1,max_length=3)


class ReviewDecision(BaseModel):
    action:str
    reviewer:str=Field(min_length=2,max_length=80)
    note:str=Field(min_length=3,max_length=1000)


class CopilotQuestion(BaseModel):
    question:str=Field(min_length=5,max_length=600)
    case_id:str|None=None

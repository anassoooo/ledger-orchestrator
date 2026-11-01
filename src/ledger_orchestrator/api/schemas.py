"""Validated request bodies for the local API."""

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    profile_id:str|None=Field(default=None,pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    years:list[int]|None=Field(default=None,min_length=1,max_length=201)


class ConsolidationRequest(BaseModel):
    profile_ids:list[str]=Field(min_length=1,max_length=12)


class ReviewDecision(BaseModel):
    action:str
    reviewer:str=Field(min_length=2,max_length=80)
    note:str=Field(min_length=3,max_length=1000)


class CopilotQuestion(BaseModel):
    question:str=Field(min_length=5,max_length=600)
    case_id:str|None=None

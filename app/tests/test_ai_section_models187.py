"""Preferences are isolated per section; receipt and text policies share order."""
import asyncio
import json
from unittest.mock import patch
import pytest
from ai_section_models187 import section_choice,update_choice,normalize_choice,provider_order,SETTINGS_KEY
import project_report_ai_187 as text_ai
from receipt_ai_provider import ReceiptVisionProviderChain


def test_legacy_choice_migrates_without_cross_section_changes():
    old={'ai_engine_mode':'GEMINI','other':'preserved'}
    new=update_choice(old,'management',{'mode':'SELECTED','models':['OPENAI','GEMINI']})
    assert section_choice('data_entry',new)['models']==['GEMINI']
    assert section_choice('calendar',new)['models']==['GEMINI']
    assert section_choice('management',new)['models']==['OPENAI','GEMINI']
    assert old=={'ai_engine_mode':'GEMINI','other':'preserved'}
    assert new['ai_engine_mode']=='GEMINI'


def test_all_updates_each_section_and_group_modes_clear_ticks():
    new=update_choice({'ai_engine_mode':'OPENAI'},'all',{'mode':'ALL','models':['GEMINI']})
    assert all(section_choice(key,new)=={'mode':'ALL','models':[]} for key in ('data_entry','management','calendar'))
    assert new['ai_engine_mode']=='ALL'


def test_at_most_three_valid_ordered_models():
    assert normalize_choice({'mode':'SELECTED','models':['OPENAI','GEMINI','OPENAI']})['models']==['OPENAI','GEMINI']
    for selected in ([],['invalid'],['OPENAI','GEMINI','OPENROUTER:QWEN','GROQ:LLAMA4']):
        with pytest.raises(ValueError):normalize_choice({'mode':'SELECTED','models':selected})


def test_provider_order_respects_priority_and_gemini_key_rotation():
    choice={'mode':'SELECTED','models':['OPENAI','GEMINI']}
    assert provider_order(choice,['GEMINI:x','GEMINI:x#2','OPENAI','OPENROUTER:QWEN'],[])==['OPENAI','GEMINI:x','GEMINI:x#2']


def test_text_falls_back_when_higher_priority_response_is_invalid(monkeypatch):
    calls=[]
    monkeypatch.setattr(text_ai,'_model_config',lambda key,*a:(key,'key','model','fake'))
    def single(prompt,engine,**kwargs):
        calls.append(engine)
        return engine,'invalid' if engine=='OPENAI' else '{"record_ids":[]}'
    monkeypatch.setattr(text_ai,'_generate_single_project_text',single)
    model,value=text_ai.generate_project_text('safe query',base_dir='.',ui_settings={},section='management',
        selection={'mode':'SELECTED','models':['OPENAI','GEMINI']},validator=json.loads)
    assert model=='GEMINI' and calls==['OPENAI','GEMINI']


def test_live_receipt_choices_do_not_follow_calendar_or_management():
    calls=[]
    class Parser:
        def __init__(self,name):self.name=name
        async def analyze(self,**kw):calls.append(self.name);return {'confidence':.99}
    chain=ReceiptVisionProviderChain([])
    chain._all_providers187=[('GEMINI:x',Parser('gemini')),('OPENAI',Parser('openai'))]
    chain._automatic_names187=['GEMINI:x'];chain._section_settings187=True
    ui=update_choice({'ai_engine_mode':'GEMINI'},'management','OPENAI')
    with patch('v18_store.load_ui',return_value=ui):asyncio.run(chain.analyze(text='test'))
    assert calls==['gemini']
    ui=update_choice(ui,'data_entry','OPENAI')
    with patch('v18_store.load_ui',return_value=ui):asyncio.run(chain.analyze(text='test'))
    assert calls==['gemini','openai']


def test_all_text_models_run_and_choose_valid_consensus(monkeypatch):
    calls=[]
    monkeypatch.setattr(text_ai,'_model_config',lambda key,*a:(key,'key','model','fake'))
    def single(prompt,engine,**kwargs):
        calls.append(engine)
        return engine,'{"record_ids":["different"]}' if engine=='GEMINI' else '{"record_ids":["registered"]}'
    monkeypatch.setattr(text_ai,'_generate_single_project_text',single)
    _,answer=text_ai.generate_project_text('test',engine='ALL',base_dir='.',ui_settings={},validator=json.loads)
    assert len(calls)==5 and json.loads(answer)['record_ids']==['registered']

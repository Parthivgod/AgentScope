import httpx
import asyncio

async def run():
    async with httpx.AsyncClient() as client:
        res = await client.post('http://localhost:8000/ingest', headers={'Authorization': 'Bearer test-key'}, json={'trace_id':'a','span_id':'b','span_type':'llm_call','name':'a','start_time':'2024-01-01T00:00:00Z','agent_id':'a'})
        print(res.status_code, res.text)

asyncio.run(run())

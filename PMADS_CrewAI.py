# This program analyzes a company's non-financial credit repayment ability using a provided company JSON file,
# combined with web search results, through a structured Karl Popper Debate framework.

import os
import re
import json
from datetime import datetime
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
from langchain_openai import ChatOpenAI
import subprocess

# 1. Load environment variable
load_dotenv()

collected_search_info = []


try:
    from crewai_tools import SerpApiGoogleSearchTool
    # Initialize the tool with default settings to avoid parameter errors
    websearch_tool = SerpApiGoogleSearchTool()

    # Validate the API key using the correct parameter
    test_result = websearch_tool._run(search_query="test")
    if "error" in str(test_result).lower():
        print("⚠️ SerpAPI 오류 발생. 웹 검색 없이 토론을 진행합니다.")
        print(f"  오류 내용: {test_result}")
        print("  💡 참고: SerpAPI 서비스 일시적 장애일 수 있습니다.")
        websearch_tool = []
    else:
        print("✅ SerpAPI 웹검색 도구가 활성화되었습니다!")
        
except ImportError:
    # Fall back to an empty list if crewai_tools is not installed
    websearch_tool = []
    print("⚠️ SerpAPI 도구를 사용할 수 없습니다.")
except ValueError as e:
    print(f"⚠️ SerpAPI 설정 오류: {e}")
    print(f"⚠️ 환경 변수 SERPAPI_API_KEY 확인: {os.environ.get('SERPAPI_API_KEY', '설정되지 않음')}")
    websearch_tool = []
except Exception as e:
    print(f"⚠️ SerpAPI 초기화 중 예상치 못한 오류: {e}")
    websearch_tool = []


# 2. Load company data
with open("/Users/mhkim/Desktop/SNU/KB/agents/ver2_에이스엔지니어링_full_analysis_20250717_182449.json", "r", encoding="utf-8") as f:
    company_data = json.load(f)

# 2-1. Extract company name from JSON
company_name = company_data.get("company_name", "성림첨단산업")
    

# 3. Generate company summary (same as before)
def generate_company_summary(data: dict) -> str:
    non_financial_info = data.get('non_financial_info', {})
    # DART is an integrated electronic corporate disclosure system operated by the Financial Supervisory Service (FSS) of South Korea.
    dart_info = data.get('dart_analysis', {})

    # Retrieve industry analysis information
    industry = non_financial_info.get('산업분석', 'N/A')

    # Retrieve corporate governance information
    governance = non_financial_info.get('지배구조', 'N/A')

    # Retrieve news information
    news = non_financial_info.get("뉴스", [])
    if isinstance(news, list) and news:
        news_titles_list = [f"- {n.get('title', 'No title')}" for n in news[:5]]
        news_titles = "\n".join(news_titles_list)
    else:
        news_titles = "  - N/A"

    # Retrieve number of employees information
    employees_list = non_financial_info.get('고용보험', [{'total_employees': 'N/A'}])
    employees = employees_list[0].get('total_employees', 'N/A') if isinstance(employees_list, list) and employees_list else 'N/A'

    # Retrieve patent information
    patents = non_financial_info.get("특허", [])
    patents_count = len(patents) if isinstance(patents, list) else 0

    if patents_count > 0 and isinstance(patents, list):
        patents_titles = [p.get('title', 'No title') for p in patents[:5]]
        patents_titles_md = "\n".join([f"  - {title}" for title in patents_titles])
        patents_part = (
            f"#### Number of Patents:\n"
            f"{patents_count}\n\n"
            f"- Representative Patent Titles:\n"
            f"{patents_titles_md}"
        )
    else:
        patents_part = f"#### Number of Patents:\n0"

    # Retrieve management/executive information
    executive_stability = non_financial_info.get('경영진', {}).get('stability_score', 'N/A')
    # Retrieve company size information
    company_size = non_financial_info.get('기업규모', 'N/A')
    certification = non_financial_info.get('인증', {})
    # innobiz and mainbiz are business certifications issued by the Korean government
    innobiz = certification.get('innobiz_certified')
    innobiz = 'N/A' if innobiz in [None, 'null'] else innobiz
    mainbiz = certification.get('mainbiz_certified')
    mainbiz = 'N/A' if mainbiz in [None, 'null'] else mainbiz
    dart_analysis = dart_info.get('gpt_analysis', 'N/A')

    summary = f"""

#### Industry / Sector Analysis:
  {industry}

#### Corporate Governance:
  {governance}

#### Number of Employees:
  {employees}

#### Patents:
  {patents_part}

#### Management Stability:
  {executive_stability}

#### Company Size:
  {company_size}

#### Certifications:
- Innobiz: {innobiz}
- Mainbiz: {mainbiz}

#### Recent News Headlines (up to 5):
  {news_titles}

#### DART Key Summary:
   {dart_analysis}

"""
    
    # Append web search results collected during the debate
    if collected_search_info:
        summary += "\n\n#### Web Search Results Collected During Debate:\n"
        for i, search_info in enumerate(collected_search_info, 1):
            # Display as a markdown link when both title and URL are available
            if search_info.get('title') and search_info.get('url'):
                title = search_info['title']
                url = search_info['url']
                summary_text = search_info.get('summary', search_info.get('content', 'N/A'))

                summary += f"\n**{i}. [{title}]({url})**\n"
                summary += f"- Searcher: {search_info.get('agent', search_info['query'])}\n"
                summary += f"- Collected at: {search_info['timestamp']}\n"
                summary += f"- Summary: {summary_text}\n"
            else:
                # Fall back to plain format when only a URL is available
                summary += f"\n**{i}. Search Topic: {search_info['query']}**\n"
                summary += f"- Collected at: {search_info['timestamp']}\n"
                content = search_info.get('content', search_info.get('summary', 'N/A'))
                summary += f"- Content: {content[:500]}{'...' if len(content) > 500 else ''}\n"
                if search_info.get('url'):
                    summary += f"- Source: {search_info['url']}\n"
            summary += "\n"
    
    return summary.strip()

# Perform pre-debate web searches before the debate begins
def perform_pre_debate_search():
    """Run baseline web searches before the debate starts."""
    global collected_search_info, websearch_tool
    
    if websearch_tool and websearch_tool != []:
        search_queries = [
            f"{company_name} 2026년 최신 뉴스",
            f"{company_name} 재무현황 2025 2026",
            f"{company_name} ESG 경영 지속가능성",
            f"{company_name} 기술개발 R&D 투자"
        ]
        
        for query in search_queries:
            try:
                print(f"🔍 사전 검색 수행: {query}")
                # Use the correct parameter name for the API call
                search_result = websearch_tool._run(search_query=query)

                # Debug: log the type and length of the search result
                print(f"  📊 Result type: {type(search_result)}")
                print(f"  📊 Result length: {len(str(search_result))}")

                # Check for error responses
                if "error" in str(search_result).lower() or "unauthorized" in str(search_result).lower():
                    print(f"  ❌ SerpAPI error: {search_result}")
                    continue

                # Parse the search result into structured data
                parsed_results = parse_search_result(search_result, query, "Pre-debate search")
                print(f"  ✅ 파싱된 결과: {len(parsed_results)}개")
                for result in parsed_results:
                    collected_search_info.append(result)
                
            except Exception as e:
                print(f"⚠️ 검색 실패 ({query}): {e}")
                continue
    else:
        print("⚠️ 검색 도구를 사용할 수 없어 사전 검색을 건너뜁니다.")

def parse_search_result(search_result, query, agent_name):
    """Parse a search result into structured data (improved version)."""
    results = []
    
    try:
        import json
        import re
        
        print(f"    🔍 파싱 시작 - 타입: {type(search_result)}")
        
        # 1. Handle dict-type SerpAPI response (preferred)
        if isinstance(search_result, dict):
            print(f"    📊 Processing dict-type response...")
            if 'organic_results' in search_result:
                organic_results = search_result['organic_results']
                print(f"    ✅ organic_results found: {len(organic_results)} items")

                for i, result in enumerate(organic_results[:3]):  # up to 3 results
                    title = result.get('title', 'No title')
                    url = result.get('link', '#')
                    snippet = result.get('snippet', 'No content')

                    if title and url and snippet:
                        # Summarize to 2-3 sentences
                        summary_sentences = snippet.split('.')[:2]
                        summary = '. '.join(s.strip() for s in summary_sentences if s.strip()) + '.'
                        
                        results.append({
                            "query": query,
                            "title": title,
                            "url": url,
                            "summary": summary[:200] + "..." if len(summary) > 200 else summary,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "agent": agent_name
                        })
                        print(f"    ✅ 결과 {i+1} 파싱 완료: {title[:50]}...")
        
        # 2. Handle string-type response (fallback)
        elif isinstance(search_result, str):
            print(f"    📊 Processing string-type response...")
            # Search for JSON pattern within the string
            json_pattern = r'\{.*?"organic_results".*?\}'
            json_matches = re.findall(json_pattern, search_result, re.DOTALL)

            for json_match in json_matches:
                try:
                    result_data = json.loads(json_match)
                    if 'organic_results' in result_data:
                        for result in result_data['organic_results'][:3]:  # up to 3 results
                            title = result.get('title', 'No title')
                            url = result.get('link', '#')
                            snippet = result.get('snippet', 'No content')

                            # Summarize to 2-3 sentences
                            summary_sentences = snippet.split('.')[:2]
                            summary = '. '.join(s.strip() for s in summary_sentences if s.strip()) + '.'
                            
                            results.append({
                                "query": query,
                                "title": title,
                                "url": url,
                                "summary": summary[:200] + "..." if len(summary) > 200 else summary,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "agent": agent_name
                            })
                except json.JSONDecodeError:
                    continue
            
            # Plain-text fallback: extract URL and summary from raw text
            if not results:
                # Extract URLs from the plain text
                url_pattern = r'https?://[^\s\])]+'
                urls = re.findall(url_pattern, search_result)

                if urls:
                    # Use the first URL found
                    url = urls[0]
                    # Extract a summary from the search result text
                    summary = search_result[:300] + "..." if len(search_result) > 300 else search_result

                    results.append({
                        "query": query,
                        "title": f"Search result: {query}",
                        "url": url,
                        "summary": summary,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "agent": agent_name
                    })
        
        print(f"    📊 총 {len(results)}개의 결과 파싱 완료")
    
    except Exception as e:
        print(f"⚠️ 검색 결과 파싱 실패: {e}")
    
    return results

# Execute pre-debate search using the corrected API call method
perform_pre_debate_search()

company_summary = generate_company_summary(company_data)


# 4. Common guidelines
guideline = """
* JSON 데이터 내에 있는 데이터는 비재무 정보로 사용될 수 있습니다. 비재무 정보는 뉴스, 재무 데이터, 인증 정보, 특허 등이 있습니다.
※ 아래 비재무 요소 판단 가이드라인을 따르되 JSON 데이터 내에 있는 데이터 중 아래 판단 가이드라인에 해당되지 않는 요소는 맥락에 따라 (+) 또는 (-)로 해석하십시오.

[비재무 요소 판단 가이드라인]
| 비재무 요소 | 해석 기준 |
|-------------|------------|
| 산업의 성장 전망 | 높을수록 (+) |
| 산업 내 경쟁 강도 | 심할수록 (-) |
| 기술 변화 파급력 | 클수록 (-) |
| 경기 민감도 | 민감할수록 (-) |
| 정부 지원사업 | 존재 시 (+) |
| 내부통제 리스크 | 클수록 (-) |
| 경영진 연속성 | 안정적일수록 (+) |
| 고용 안정성 | 높을수록 (+) |
| 인증 여부 (이노비즈 등) | 있으면 (+) |
| 검색량 추이 | 증가 시 (+) |
※ (+): 여신상환능력 긍정 신호 / (-): 여신상환능력 부정 신호 / (+/-): 맥락에 따라 여신상환능력에 미치는 영향이 다름. 기업 여신 상환 전문가로서 면밀한 판단이 필요함.

※ 동일한 비재무 요소를 찬반이 반복해서 사용하지 마십시오.
※ 각 발언은 서로 다른 비재무 요소를 반드시 포함해야 하며, 가능한 한 뉴스, 지배구조, 특허, 인증 등 company_summary가 아닌, company_data JSON에 포함된 다양한 항목을 고르게 활용하십시오.
※ 같은 요소라도 서로 다른 세부 데이터(연도, 수치, 사건 등)를 근거로 한다면 추가 사용 가능하지만, 반드시 구체적으로 구분하여 서술하십시오.
※ Karl Popper Debate의 목적은 다양한 관점을 통해 리스크와 기회를 폭넓게 검토하는 것이므로, 서로 다른 (+)/(+/-)/(-) 신호를 균형 있게 사용하십시오.

[최신 정보 우선 사용 원칙]
※ JSON 데이터 내에서 동일한 항목에 대해 여러 시점의 정보가 존재할 경우, 반드시 가장 최신 날짜/연도의 데이터를 우선적으로 사용하십시오.
※ 뉴스, 재무 데이터, 인증 정보, 특허 등에서 날짜 정보가 명시된 경우 최신순으로 정렬하여 최신 정보를 우선 인용하십시오.
※ 뉴스 정보는 최신 정보를 우선 인용하되, 뉴스 정보가 부족하거나 생략된 경우, 반드시 SerpAPISearchTool을 사용하여 최신 뉴스를 검색하고 보강하십시오. 
  [케이스 1 - 뉴스 정보 보강] 검색 키워드: '{기업명} + 최신 뉴스'
※ 반박이나 논증에 필요한 정보가 JSON 데이터에 충분하지 않은 경우, 반드시 SerpAPISearchTool을 사용하여 관련 정보를 검색하고 보강하십시오.
  [케이스 2 - 논증용 정보 보강] 검색 키워드: '{기업명} + {구체적 주제} + 최신 동향'
※ 과거 데이터를 사용할 때는 반드시 "2025년 3월 기준" 등 명확한 시점을 명시하고, 최신 트렌드와의 차이점을 고려하십시오.

"""

# Karl Popper Debate structure description (template variable)
karl_popper_explanation = """
[토론 방식: Karl Popper Debate]

이 토론은 금융사가 기업여신상환 능력을 평가하는 것을 보고하기 위해 비재무 정보를 활용하여 JSON 데이터 안의 DART 데이터 날짜 이후 기업의 여신상환능력 전망을 예측하는 것을 목적으로 합니다.
DART 데이터 날짜 이전 데이터는 주의하여 유심히 검토하십시오. 
이 토론은 Karl Popper 방식에 따라 진행하십시오. 해당 방식은 다음과 같은 규칙과 절차를 따르십시오.

1. 총 10단계 발언 구조를 반드시 유지하십시오. 10단계 발언 구조는 다음과 같습니다: A1 입론 → B3 교차질문 → B1 입론 → A3 교차질문 → A2 반론 → B1 교차질문 → B2 반론 → A1 교차질문 → A3 찬성 정리 → B3 반대 정리
2. 각 발언은 다음의 논리 구조를 따르십시오:
   - 하나의 핵심 주장 제시
   - 최소 3개의 비재무 요소를 사용하여 주장 근거 구성
   - 모든 근거는 company_summary가 아닌, company_data JSON 기반 기업 데이터에서 구체적 수치/날짜/내용을 명시적으로 인용. 최신 정보를 우선적으로 인용.
   - 해당 주장의 반증 가능성을 반드시 고려 (예외/불확실성 조건 등)

3. 모든 주장은 [비재무 요소 판단 가이드라인]에 따라 (+), (-), (+/-) 신호로 하십시오. 가이드라인에 없는 요소는 맥락에 따라 (+) 또는 (-)로 해석하십시오.

4. 창작, 과도한 추론, 데이터 외 상상은 금지되며, 반드시 주어진 입력 정보 범위 안에서 논리를 구성하십시오.

5. "토론 결과를 읽는 사용자가 여신상환능력을 평가할 수 있도록 각 주제 별로 예상 신용 영향 파악을 염두에 두고 토론을 진행"해야 합니다.

6. 만약 주어진 JSON 데이터에 대한 모든 사항이 검토되지 않았다면 논의되지 않은 정보들에 대하여 10단계 발언 구조에 따라 토론을 추가적으로 수행합니다. 모든 정보가 검토되었다면 토론을 종료합니다.

7. 토론 결과는 반드시 영어로 작성하십시오.

8. 모든 토론이 끝나면 토론 내용을 찬성, 반대 측 각각 최종 정리하십시오.
"""


# 5. Create agents
llm = ChatOpenAI(temperature=0.3, model="gpt-4o")

# Pro-side Agents
a1 = Agent(
    role="찬성팀 입론자 A1",
    goal="해당 기업의 비재무 정보를 근거로 여신상환능력이 향상될 것임을 Karl Popper 방식에 따라 논증하라.",
    backstory=(
        karl_popper_explanation +
        "\n\n당신은 Karl Popper 방식의 토론에 능숙한 낙관적인 금융 분석가입니다.\n"
        "첫 번째 입론자로서, 핵심 주장 하나를 중심으로 최소 3개의 여신상환능력이 향상되는 데에 기여할 수 있는 비재무 요소를 논리적 근거로 사용하고,"
        "구체적인 데이터 인용과 함께 반증 가능성을 반드시 포함한 주장을 작성하십시오. All responses must be written in English.\n"
        "[케이스 1] 뉴스 정보 부족 시: '{기업명} + 최신 뉴스' 키워드로 SerpAPISearchTool 사용\n"
        "\n\n※ JSON에 포함된 정보 중 가장 최신 시점의 데이터를 우선 인용하십시오."
    ),
    llm=llm,
    tools=[websearch_tool] if websearch_tool and websearch_tool != [] else []
)

a2 = Agent(
    role="찬성팀 반론자 A2",
    goal=(
        "반대팀의 입론을 Karl Popper 방식에 따라 조목조목 반박하라.\n"
        "[케이스 2] 반박용 정보 부족 시: '{기업명} + {구체적 주제} + 최신 동향' 키워드로 SerpAPISearchTool 사용하여 신뢰할 수 있는 출처의 정보를 인용하라."
    ),
    backstory=(
        karl_popper_explanation +
        "\n\n당신은 Karl Popper 방식의 토론에 능숙한 낙관적인 금융 분석가로서, 반대측 입론의 논거 중 해석 오류, 논리적 약점,데이터 불확실성을 지적하십시오. 이를 위해 적합한 정보가 JSON 데이터에 존재하지 않는다고 판단될 경우 실시간으로 웹검색을 수행하여 반론의 근거를 삼을 정보를 찾아 활용하십시오.\n"
        "[케이스 2] 논증용 정보 부족 시: '{기업명} + {구체적 주제} + 최신 동향' 키워드로 SerpAPISearchTool 사용\n"
        "\n\nAll responses must be written in English."
        "\n\n※ JSON에 포함된 정보 중 가장 최신 시점의 데이터를 우선 인용하십시오."
    ),
    llm=llm,
    tools=[websearch_tool] if websearch_tool and websearch_tool != [] else []
)

a3 = Agent(
    role="찬성팀 정리자 및 교차조사자 A3",
    goal="반대팀 발언에 대한 교차질문을 구성하고 찬성 측 주장을 요약 정리하라.",
    backstory=(
        karl_popper_explanation +
        "\n\n당신은 논리적 교차질문 및 정리 능력이 뛰어난, Karl Popper 방식의 토론에 능숙하고 비판적 사고와 요약 정리에 뛰어난 낙관적인 능숙한 금융 분석가입니다.\n"
        "반대측 발언에 논리적 약점을 지적하는 질문 3개를 작성하고, 찬성 측의 전체 주장을 일관되게 정리하여 설득력 있게 마무리하십시오.\n"
        "All responses must be written in English."
    ),
    llm=llm
)

# Con-side Agents
b1 = Agent(
    role="반대팀 입론자 B1",
    goal="해당 기업의 비재무 정보를 근거로 여신상환능력이 향상될 것이라는 주장에 대해 Karl Popper 방식으로 논리적 반론을 제시하라.",
    backstory=(
        karl_popper_explanation +
        "\n\n당신은 Karl Popper 방식의 토론에 능숙한 비관적인 금융 리스크 분석 전문가입니다. 반대측 입론자로서 핵심 반대 주장 하나를 제시하고,"
        "여신상환능력 변동에 영향을 미칠 최소 3개의 부정적(-) 또는 불확실한(+/-) 신호로 해석 가능한 비재무 요소를 근거로 사용해 논리를 전개해야 합니다.\n"
        "데이터 기반 인용과 반증 가능성 고려는 필수입니다.\n"
        "All responses must be written in English.\n"
        "[케이스 1] 뉴스 정보 부족 시: '{기업명} + 최신 뉴스' 키워드로 SerpAPISearchTool 사용\n"
        "\n\n※ JSON에 포함된 정보 중 가장 최신 시점의 데이터를 우선 인용하십시오."
    ),
    llm=llm,
    tools=[websearch_tool] if websearch_tool and websearch_tool != [] else []
)

b2 = Agent(
    role="반대팀 반론자 B2",
    goal=(
        "찬성팀의 입론을 Karl Popper 방식에 따라 조목조목 반박하라.\n"
        "[케이스 2] 반박용 정보 부족 시: '{기업명} + {구체적 주제} + 최신 동향' 키워드로 SerpAPISearchTool 사용하여 신뢰할 수 있는 출처의 정보를 인용하라."
    ),
    backstory=(
        karl_popper_explanation +
        "\n\n당신은 Karl Popper 방식의 토론에서 구조화된 반론 전략에 능숙한 비관적인 금융 분석가입니다. 찬성측 주장에 나타난 해석상의 과도한 낙관,"
        "자료 불일치, 대안 가능성 등을 지적하고, 이를 약화시키는 반례나 예외 조건을 데이터 기반으로 제시해야 합니다.\n"
        "정보 풀에 존재하지 않는 경우에는 실시간으로 검색해 부족한 Fact를 보완하여 반론의 근거로 삼아야 합니다.\n"
        "[케이스 2] 논증용 정보 부족 시: '{기업명} + {구체적 주제} + 최신 동향' 키워드로 SerpAPISearchTool 사용\n"
        "\n\nAll responses must be written in English."
        "\n\n※ JSON에 포함된 정보 중 가장 최신 시점의 데이터를 우선 인용하십시오."
    ),
    llm=llm,
    tools=[websearch_tool] if websearch_tool and websearch_tool != [] else []
)

b3 = Agent(
    role="반대팀 정리자 및 교차조사자 B3",
    goal="찬성팀 발언에 대한 교차질문을 구성하고 반대 측 주장을 최종 정리하라.",
    backstory=(
        karl_popper_explanation +
        "\n\n당신은 논리적 교차질문 및 정리 능력이 뛰어난, Karl Popper 방식의 토론에 능숙하고 비판적 사고와 요약 정리에 뛰어난 비관적인 금융 분석가입니다.\n"
        "찬성측 주요 발언에 대해 논리적 약점을 지적하는 질문 3개를 작성하고, 찬성 측의 전체 주장을 일관되게 정리하여 설득력 있게 마무리하십시오.\n"
        "All responses must be written in English."
    ),
    llm=llm
)

# Aggregator Agent
aggregator = Agent(
    role="Aggregator Agent",
    goal=(
        f"{company_name}의 여신상환능력에 대한 Karl Popper Debate의 모든 발언, 교차질문, 반론을 종합하여"
        "토론의 흐름과 각 입장별 논리 구조를 일관성 있게 정리하고,"
        "최종 결과물의 '토론 내역' 파트를 작성한다."
    ),
    backstory=(
        f"당신은 {company_name}의 토론 흐름과 정보 논리를 종합해 문서화하는 전문가입니다.\n\n"
        f"각 팀의 주장, 반론, 교차질문을 논리적으로 연결해 {company_name}에 대한 하나의 보고서 형태로 정리해야 합니다.\n"
        "각 에이전트의 발언을 모니터링하여 토론 내역을 정리하고 논리적 일관성을 점검해야 합니다.\n"
        "모든 정보는 이미 제공된 데이터 풀과 토론 중 검색된 자료를 기반으로 작성합니다."
        "\n\n※ JSON에 포함된 정보 중 가장 최신 시점의 데이터를 우선 인용하십시오.\n\n"
        "⚡️ 교차질문과 반론 단계에서 새로 인용된 요소도 pros/cons에 반드시 포함할 것."
        "⚡️ 동일한 요소라도 다른 데이터(시점/수치/맥락)를 포함하면 별도 항목으로 구분할 것."
    ),
    llm=llm
)


# 6. Define tasks
# Uses the karl_popper_explanation variable defined above
# Note: In the current version, each debate step only receives the context it is deemed to need.
# However, since participants in a real human debate can hear all prior exchanges,
# an alternative approach is to accumulate context across every step (i.e., pass all previous task outputs to each subsequent task).

guideline_text = karl_popper_explanation + guideline + f"\n\n[분석 대상 기업: {company_name}]\n" \
"[모든 발언은 company_summary가 아닌, company_data JSON 데이터 기반으로 작성되어야 하며," \
"명확한 수치·시점 인용 및 반증 가능성을 포함해야 합니다. 창작과 추론은 금지됩니다.]\n" \
f"[🔍 SerpAPI 검색 가이드라인 - 2026년 최신 정보 우선 활용]\n" \
f"케이스 1 - 뉴스 정보 부족 시: '{company_name} + 2026년 + 최신 뉴스' 키워드로 검색\n" \
f"케이스 2 - 논증용 정보 부족 시: '{company_name} + {{구체적 주제}} + 2026년 + 최신 동향' 키워드로 검색\n" \
"⚠️ 검색 결과에서 반드시 2026년 또는 2025년 하반기 이후 정보를 우선 선택하여 인용\n" \
"⚠️ 검색된 정보의 날짜를 명시하고, 오래된 정보(2025년 상반기 이전)는 사용 지양\n"

# 6-1. A1 Opening Statement (Pro)
task_1 = Task(
    description=(
        guideline_text +
        "\n\n당신은 찬성팀 입론자 A1입니다. 기업의 여신상환능력이 향상될 것이라는 주장 하나를 제시하고,"
        "이를 3개 이상의 (+) 비재무 요소에 근거하여 600자 이내로 구성하십시오.\n"
        "각 요소는 company_summary가 아닌, company_data JSON 데이터에서 수치/날짜를 명확히 인용하고, 반증 가능성도 반드시 제시하십시오.\n"
        "All responses must be written in English."
        "\n\n※ JSON에 포함된 정보 중 가장 최신 시점의 데이터를 우선 인용하십시오."
        f"\n\n🔥 2026년 최신 정보 필수 활용: 필요시 '{company_name} + 2026년 + 최신 뉴스' 검색을 통해 최신 동향을 적극 반영하십시오."
        "⚡️ 주의: 이 입론/반론/질문에서는 반드시 이전 발언과 중복되지 않는 새로운 비재무 요소를 선택하여 주장해야 합니다."
    ),
    expected_output="600자 이내 찬성 입론: 핵심 주장 + (+) 요소 3개 이상 + 인용 + 반증 가능성",
    agent=a1
)

# 6-2. B3 Cross-Examination (targeting A1's opening statement)
task_2 = Task(
    description=(
        guideline_text +
        "\n\n당신은 반대팀 B3입니다. 찬성팀 A1의 입론을 대상으로 교차질문 3개를 작성하십시오.\n"
        "각 질문은 인용된 비재무 요소 중 2개 이상에 대해 해석 오류, 데이터 신뢰성, 반례 가능성 등을 겨냥해야 합니다.\n"
        "All responses must be written in English."
        "⚡️ 교차질문 시에는 반복된 요소가 아닌, 상대 발언에 등장한 다른 요소의 해석 오류나 대안 가능성을 지적하십시오."
    ),
    expected_output="논리적 교차질문 3개 (A1 입론 대상)",
    agent=b3,
    context=[task_1]
)

# 6-3. B1 Opening Statement (Con)
task_3 = Task(
    description=(
        guideline_text +
        "\n\n당신은 반대팀 입론자 B1입니다. 기업의 여신상환능력에 부정적/불확실한 전망을 주장하며,"
        "최소 3개 이상의 (-) 또는 (+/-) 요소를 company_summary가 아닌, company_data JSON 데이터 기반으로 인용하여 입론을 구성하십시오.\n"
        "All responses must be written in English."
        "\n\n※ JSON에 포함된 정보 중 가장 최신 시점의 데이터를 우선 인용하십시오."
        f"\n\n🔥 2026년 최신 정보 필수 활용: 필요시 '{company_name} + 2026년 + 최신 뉴스' 검색을 통해 최신 동향을 적극 반영하십시오."
        "⚡️ 주의: 이 입론/반론/질문에서는 반드시 이전 발언과 중복되지 않는 새로운 비재무 요소를 선택하여 주장해야 합니다."
    ),
    expected_output="600자 이내 반대 입론: 핵심 주장 + 요소 3개 이상 + 인용 + 반증 고려",
    agent=b1
)

# 6-4. A3 Cross-Examination (targeting B1's opening statement)
task_4 = Task(
    description=(
        guideline_text +
        "\n\n당신은 찬성팀 A3입니다. 반대팀 B1의 입론 중 인용된 비재무 요소 2개 이상을 골라,"
        "논리적 반례나 해석 오류 가능성을 지적하는 교차질문 3개를 작성하십시오.\n"
        "All responses must be written in English."
        "⚡️ 교차질문 시에는 반복된 요소가 아닌, 상대 발언에 등장한 다른 요소의 해석 오류나 대안 가능성을 지적하십시오."
    ),
    expected_output="논리적 교차질문 3개 (B1 입론 대상)",
    agent=a3,
    context=[task_3]
)

# 6-5. A2 Rebuttal (Pro side, countering B1's opening statement)
task_5 = Task(
    description=(
        guideline_text +
        "\n\n당신은 찬성팀 반론자 A2입니다. 반대팀 B1의 주장에 대해 논리적으로 반박하십시오.\n"
        "주장된 요소의 불확실성, 다른 해석 가능성, 반례 등을 지적하여 찬성 입장을 강화해야 합니다.\n"
        f"[케이스 2] 논증용 정보 부족 시: '{company_name} + {{구체적 주제}} + 2026년 + 최신 동향' 키워드로 SerpAPISearchTool 사용하여 신뢰할 수 있는 언론/공식자료만 인용하라.\n"
        "All responses must be written in English."
        "\n\n※ JSON에 포함된 정보 중 가장 최신 시점의 데이터를 우선 인용하십시오."
        "\n\n🔥 2026년 최신 정보 필수 활용: 웹검색 시 반드시 '2026년' 키워드를 포함하여 최신 동향과 뉴스를 적극 활용하십시오."
    ),
    expected_output="400자 내외 논리적 반론 (B1 주장 반박 + 데이터 인용)",
    agent=a2,
    context=[task_3]
)

# 6-6. B1 Cross-Examination (targeting A2's rebuttal)
task_6 = Task(
    description=(
        guideline_text +
        "\n\n당신은 반대팀 B1입니다. A2의 반론에 대해 논리적 허점을 짚는 교차질문 3개를 작성하십시오.\n"
        "찬성 측 반박 근거의 신뢰성, 해석 일관성, 반증 가능성에 대해 질문하십시오.\n"
        "All responses must be written in English."
        "⚡️ 교차질문 시에는 반복된 요소가 아닌, 상대 발언에 등장한 다른 요소의 해석 오류나 대안 가능성을 지적하십시오."
    ),
    expected_output="논리적 교차질문 3개 (A2 반론 대상)",
    agent=b1,
    context=[task_5]
)

# 6-7. B2 Rebuttal (Con side, countering A1's opening statement)
task_7 = Task(
    description=(
        guideline_text +
        "\n\n당신은 반대팀 B2입니다. 찬성팀 A1의 입론을 대상으로 직접 반론을 제시하십시오.\n"
        "핵심 근거의 맥락 해석 오류, 불확실성, 부정적 재해석 등을 기반으로 주장에 반박하십시오.\n"
        f"[케이스 2] 논증용 정보 부족 시: '{company_name} + {{구체적 주제}} + 2026년 + 최신 동향' 키워드로 SerpAPISearchTool 사용하여 신뢰할 수 있는 언론/공식자료만 인용하라.\n"
        "All responses must be written in English."
        "\n\n※ JSON에 포함된 정보 중 가장 최신 시점의 데이터를 우선 인용하십시오."
        "\n\n🔥 2026년 최신 정보 필수 활용: 웹검색 시 반드시 '2026년' 키워드를 포함하여 최신 동향과 뉴스를 적극 활용하십시오."
    ),
    expected_output="400자 내외 반론 (찬성 입론에 대한 반대 측 반박)",
    agent=b2,
    context=[task_1]
)

# 6-8. A1 Cross-Examination (targeting B2's rebuttal)
task_8 = Task(
    description=(
        guideline_text +
        "\n\n당신은 찬성팀 A1입니다. 반대팀 B2의 반론 주장에 대해 교차질문 3개를 구성하십시오.\n"
        "해당 반론의 논리적 근거, 반례 가능성, 해석 오류 등을 지적할 수 있는 질문이어야 합니다.\n"
        "All responses must be written in English."
        "⚡️ 교차질문 시에는 반복된 요소가 아닌, 상대 발언에 등장한 다른 요소의 해석 오류나 대안 가능성을 지적하십시오."
    ),
    expected_output="논리적 교차질문 3개 (B2 반론 대상)",
    agent=a1,
    context=[task_7]
)

# 6-9. A3 Closing Summary (Pro team)
task_9 = Task(
    description=(
        guideline_text +
        "\n\n당신은 찬성팀 A3입니다. 찬성팀 A1, A2의 주장과 교차질문, 반대측 주장에 대한 대응 논리를 종합하여"
        "600자 내외로 전체 요약 정리를 하십시오. 새로운 주장은 추가하지 마십시오.\n"
        "All responses must be written in English."
    ),
    expected_output="600자 내외 찬성 측 최종 정리 요약",
    agent=a3,
    context=[task_1, task_2, task_5, task_8]
)

# 6-10. B3 Closing Summary (Con team)
task_10 = Task(
    description=(
        guideline_text +
        "\n\n당신은 반대팀 B3입니다. 반대팀 B1, B2의 주장과 교차질문, 찬성측 주장에 대한 반론 논리를 종합하여"
        "600자 내외로 최종 정리를 작성하십시오. 새로운 근거를 도입하지 마십시오.\n"
        "All responses must be written in English."
    ),
    expected_output="600자 내외 반대 측 최종 정리 요약",
    agent=b3,
    context=[task_3, task_4, task_7, task_6]
)


# 7. Aggregate and summarize all debate content (Aggregator)
task_11 = Task(
    description=(
        "You are the Aggregator Agent of the Karl Popper Debate.\n\n"
        "Once all debate rounds are complete, compile and return the debate results as a JSON object written in the style of a senior financial professional. The debate may run through the 10-step structure multiple times.\n"
        "Group each item by 'non-financial factor topic' and summarize the pro and con positions for each topic.\n"
        "All points must be grounded in actual statements made during the debate, and sources must be included where cited.\n\n"
        "The output format must follow the example below and must be enclosed in a ```json code block```:\n"
        "```json\n"
        "{\n"
        "  \"debate_summary\": {\n"
        "    \"positive_factors_summary\": [\n"
        "      \"The company completed commercialization of its new technology in Q1 2026, improving production efficiency by over 15%. A three-year long-term supply contract signed in February of the same year enhances cash flow visibility and is expected to strengthen credit repayment stability.\",\n"
        "      \"An environmental compliance certification obtained in March improves brand image and lays the groundwork for expanding opportunities in public and government-backed projects.\",\n"
        "      \"Taken together, these factors are expected to contribute positively to the company's profitability and long-term business sustainability.\"\n"
        "    ],\n"
        "    \"negative_factors_summary\": [\n"
        "      \"The technology commercialization phase may require a longer-than-expected market validation period and additional capital investment.\",\n"
        "      \"Underperformance by key customers could introduce uncertainty in the actual execution of long-term supply contracts, and early termination would undermine revenue stability.\",\n"
        "      \"Tightening environmental regulations from the second half of 2026 may lead to additional capital expenditures and higher operating costs, posing a short-term financial burden.\",\n"
        "      \"These risk factors may exert negative pressure on the company's credit repayment ability and warrant close monitoring.\"\n"
        "    ],\n"
        "    \"topics\": [\n"
        "      {\n"
        "        \"topic\": \"Supply Chain Stability\",\n"
        "        \"pro\": \"Diversification strategy underway → potential risk mitigation. [Ministry of Industry Supply Chain Brief (2024)]. Reduced supply risk → sustainable revenue maintenance.\",\n"
        "        \"con\": \"Quality and contractual uncertainty in alternative supply chains. [KITA Supply Chain Brief (Jan 2024)]. Prolonged supply delays → delivery failures → revenue decline and credit risk.\"\n"
        "      }\n"
        "    ]\n"
        "  }\n"
        "}\n"
        "```\n"
        "※ Each 'topic' must be named after a single non-financial factor (e.g., 'Employee Retention', 'Governance', 'Industry Growth').\n"
        "※ Either 'pro' or 'con' may be absent for a given topic; in that case, leave the missing field as an empty string rather than omitting it.\n"
        "※ No duplicate topics are allowed.\n"
        "※ Ensure the output is free of JSON formatting errors.\n"
        "※ 'positive_factors_summary' and 'negative_factors_summary' should be abstract sentence lists synthesizing the content across all topics.\n"
        "※ All content must be written in English."
    ),
    agent=aggregator,
    context=[
        task_1, task_2, task_3, task_4, task_5,
        task_6, task_7, task_8, task_9, task_10
    ],
    expected_output=(
        "{\n"
        "  \"debate_summary\": {\n"
        "    \"positive_factors_summary\": [],\n"
        "    \"negative_factors_summary\": [],\n"
        "    \"topics\": []\n"
        "  }\n"
        "}"
    )
)


# 8. Assemble the Crew
crew = Crew(
    agents=[a1, a2, a3, b1, b2, b3, aggregator],
    tasks=[
        task_1, task_2, task_3, task_4, task_5,
        task_6, task_7, task_8, task_9, task_10, task_11
    ],
    verbose=True,
    process="sequential"
)

# Run the Crew (executes the 10-step Karl Popper debate)
results = crew.kickoff()

# 9. Output results
# === Full task output ===
task_outputs = results.tasks_output

# === Collect and process web search results gathered during the debate ===
def extract_search_results_from_tasks(task_outputs):
    """Extract actual SerpAPI search results from task outputs (improved version)."""
    search_results = []
    import re
    import json
    
    print(f"🔍 {len(task_outputs)}개 Task 출력에서 검색 결과 추출 시작...")
    
    for i, task_output in enumerate(task_outputs):
        if hasattr(task_output, 'raw') and task_output.raw:
            raw_text = task_output.raw
            agent_name = getattr(task_output, 'agent', f'Agent_{i}')
            
            print(f"  📝 {agent_name} 출력 분석 중... (길이: {len(raw_text)}자)")
            
            # 1. Check for SerpAPI error messages
            if "error" in raw_text.lower() or "unauthorized" in raw_text.lower():
                print(f"    ⚠️ {agent_name}: SerpAPI error detected")
                continue

            # 2. Check for "Using Tool: Google Search" pattern
            if "Using Tool: Google Search" in raw_text:
                print(f"    🔍 {agent_name}: Google Search tool usage detected")

                # 3. Try multiple search result patterns
                patterns_tried = 0

                # Pattern 1: JSON-format organic_results
                json_pattern = r'\{[^{}]*"organic_results"[^{}]*\}'
                json_matches = re.findall(json_pattern, raw_text, re.DOTALL)
                
                for json_match in json_matches:
                    try:
                        result_data = json.loads(json_match)
                        if 'organic_results' in result_data:
                            print(f"    ✅ {agent_name}: JSON organic_results 발견 ({len(result_data['organic_results'])}개)")
                            for result in result_data['organic_results'][:3]:  # up to 3 results
                                title = result.get('title', 'No title')
                                url = result.get('link', '#')
                                snippet = result.get('snippet', 'No content')
                                
                                if title and url and snippet:
                                    summary_sentences = snippet.split('.')[:2]
                                    summary = '. '.join(s.strip() for s in summary_sentences if s.strip()) + '.'
                                    
                                    search_results.append({
                                        "query": f"SerpAPI search result ({agent_name})",
                                        "title": title,
                                        "url": url,
                                        "summary": summary[:200] + "..." if len(summary) > 200 else summary,
                                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "agent": agent_name
                                    })
                                    patterns_tried += 1
                    except json.JSONDecodeError:
                        continue
                
                # Pattern 2: General search result patterns
                search_patterns = [
                    r'"title":\s*"([^"]*)".*?"link":\s*"([^"]*)".*?"snippet":\s*"([^"]*)"',
                    r'Title:\s*([^\n]+)\nURL:\s*([^\n]+)\nSnippet:\s*([^\n]+)',
                    r'제목:\s*([^\n]+)\n링크:\s*([^\n]+)\n내용:\s*([^\n]+)'
                ]
                
                for pattern in search_patterns:
                    try:
                        matches = re.findall(pattern, raw_text, re.DOTALL)
                        for match in matches:
                            if len(match) >= 3:
                                title, url, snippet = match[0], match[1], match[2]
                                if title.strip() and url.strip() and snippet.strip():
                                    summary_sentences = snippet.split('.')[:2]
                                    summary = '. '.join(s.strip() for s in summary_sentences if s.strip()) + '.'
                                    
                                    search_results.append({
                                        "query": f"Web search result ({agent_name})",
                                        "title": title.strip(),
                                        "url": url.strip(),
                                        "summary": summary[:200] + "..." if len(summary) > 200 else summary,
                                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "agent": agent_name
                                    })
                                    patterns_tried += 1
                    except Exception as e:
                        continue
                
                # Pattern 3: URL pattern
                url_pattern = r'https?://[^\s\]]+'
                urls = re.findall(url_pattern, raw_text)
                for url in urls[:2]:  # up to 2 URLs
                    url_context = extract_url_context(raw_text, url)
                    if url_context:
                        search_results.append({
                            "query": f"Reference material ({agent_name})",
                            "title": f"Source cited during debate",
                            "url": url.strip(),
                            "summary": url_context[:150] + "..." if len(url_context) > 150 else url_context,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "agent": agent_name
                        })
                        patterns_tried += 1
                
                if patterns_tried == 0:
                    print(f"    ⚠️ {agent_name}: No search result pattern found")
                    # Save a portion of the output for debugging purposes
                    debug_text = raw_text[:500] + "..." if len(raw_text) > 500 else raw_text
                    search_results.append({
                        "query": f"Debug info ({agent_name})",
                        "title": f"Search attempted - no pattern matched",
                        "url": "#",
                        "summary": f"Raw output: {debug_text}",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "agent": agent_name
                    })
    
    # Remove duplicate results
    unique_results = []
    seen_urls = set()
    
    for result in search_results:
        url_key = result.get('url', '')
        if url_key and url_key not in seen_urls and url_key != '#':
            seen_urls.add(url_key)
            unique_results.append(result)
    
    print(f"🔍 총 {len(unique_results)}개의 고유한 검색 결과 추출 완료")
    return unique_results[:15]  # return at most 15 results

def extract_url_context(text, url):
    """Extract surrounding text around a URL."""
    try:
        url_index = text.find(url)
        if url_index == -1:
            return ""

        # Extract up to 100 characters before and after the URL
        start = max(0, url_index - 100)
        end = min(len(text), url_index + len(url) + 100)
        context = text[start:end]

        # Split into sentences and return a clean excerpt
        sentences = context.split('.')
        if len(sentences) >= 2:
            return sentences[1].strip() + '.'
        return context.strip()
    except:
        return ""

# Extract search results from task outputs
search_results = extract_search_results_from_tasks(results.tasks_output)

# Append extracted results to the global collection if any were found
if search_results:
    for result in search_results:
        collected_search_info.append(result)
    print(f"✅ Collected {len(search_results)} search-related items during the debate.")

    # Regenerate company_summary to include web search results
    company_summary = generate_company_summary(company_data)
else:
    print("⚠️ No search results were collected during the debate.")
    print("💡 The debate can still be meaningful using JSON data alone.")
    print("📊 Proceeding with in-depth analysis based on the provided company data.")

    # Regenerate company_summary (no web results to add)
    company_summary = generate_company_summary(company_data)

# === Retrieve Aggregator output ===
aggregator_output = task_outputs[-1]
raw_output = aggregator_output.raw

# === Extract JSON from code block first ===
match = re.search(r"```json(.*?)```", raw_output, re.DOTALL)
if match:
    json_text = match.group(1).strip()
    print("✅ JSON successfully extracted from code block!")
else:
    json_text = raw_output.strip()
    print("⚠️ No code block found. Attempting to parse raw output.")

# === Parse JSON ===
try:
    summary_json = json.loads(json_text)
    print("✅ JSON parsing successful!")
except json.JSONDecodeError as e:
    print("❌ JSON parsing failed:", e)
    summary_json = None


# Build the JSON report structure for the debate results (using company_summary with web search results)
company_name = company_data.get("dart_analysis", {}).get("company_name", "회사명없음")
report_date = datetime.today().strftime("%Y-%m-%d")
dart_info = company_data.get("dart_analysis", {})
non_financial = company_data.get("non_financial_info", {})

# established_year = dart_info.get("설립연도") or non_financial.get("설립연도", "(to be filled in)")
main_business = non_financial.get('산업분류', '없음')

# 1) Report purpose
section_1 = {
    "id": 1,
    "title": "Report Purpose",
    "content": f"This report aims to evaluate {company_name}'s credit repayment ability with a focus on non-financial factors, providing Relationship Managers (RMs) with substantive grounds for credit decision-making. Key arguments are derived through a Karl Popper-style structured debate, and both positive and negative perspectives on each topic are presented alongside credit impact analysis to ensure a balanced consideration of diverse risk factors."
}

# 2) Company overview (blank fields can be filled in later)
section_2 = {
    "id": 2,
    "title": "Company Overview",
    "content": {
        "Company Name": company_name,
        # "Established Year": established_year,
        "Main Business": main_business,
    }
}

section_3 = {
    "id": 3,
    "title": "Debate Summary and Key Issues",
    "content": {
        "debate_summary": (summary_json or {}).get("debate_summary", {
            "positive_factors_summary": [],
            "negative_factors_summary": [],
            "topics": []
        })
    }
}

# 4) Non-financial factors summary (uses company_summary with web search results incorporated)
section_4 = {
    "id": 4,
    "title": "Non-Financial Factors Summary",
    "content": company_summary
}

# 5) Disclaimer
section_5 = {
    "id": 5,
    "title": "Disclaimer",
    "content": (
        "A synthesis of the Karl Popper Debate findings and non-financial factors indicates that "
        f"{company_name}'s credit repayment ability is subject to both positive signals and risk factors. "
        "Accordingly, any credit decision must incorporate a comprehensive assessment of all relevant variables and risks. "
        "This report is intended for reference purposes only; final credit decisions rest on the holistic judgment of qualified professionals."
    )
}

# Assemble the final JSON structure (with web search results included)
final_report = {
    "title": "Corporate Credit Repayment Ability Assessment Report",
    "sections": [section_1, section_2, section_3, section_4, section_5]
}

# Save JSON report
final_json_path = f"{company_name}.json"
with open(final_json_path, "w", encoding="utf-8") as f:
    json.dump(final_report, f, ensure_ascii=False, indent=2)

print(f"✅ 구조화된 JSON 보고서 저장 완료: {final_json_path}")


# File paths for Markdown and PDF output
markdown_path = f"{company_name}_type2.md"
pdf_path = f"{company_name}_type2.pdf"

# Function to generate Markdown from the report JSON
def json_to_markdown(report_json: dict) -> str:
    md = []
    md.append(f"# {report_json['title']}")
    md.append(f"**Reference Date:** {report_date}\n")
    md.append("---\n")

    for section in report_json["sections"]:
        md.append(f"## {section['id']}. {section['title']}\n")

        # (2) Company overview: render as key-value pairs from dict
        if section["id"] == 2 and isinstance(section["content"], dict):
            for key, value in section["content"].items():
                md.append(f"- **{key}**: {value}")
        
        # (3) Debate summary and key issues
        elif section["id"] == 3 and isinstance(section.get("content", {}).get("debate_summary", {}).get("topics"), list):
            debate = section["content"]["debate_summary"]

            # Print summary lists
            pos_list = debate.get("positive_factors_summary", [])
            neg_list = debate.get("negative_factors_summary", [])

            if pos_list:
                md.append("### (+) Positive Factors Affecting Credit Repayment Ability")
                for item in pos_list:
                    md.append(f"- {item}")
            md.append("")
            if neg_list:
                md.append("### (-) Negative Factors Affecting Credit Repayment Ability")
                for item in neg_list:
                    md.append(f"- {item}")
            md.append("")

            # Detailed pro/con breakdown per topic
            for topic in debate.get("topics", []):
                topic_title = topic.get("topic", "Non-Financial Factor")
                pro = topic.get("pro", "")
                con = topic.get("con", "")

                md.append(f"### {topic_title}")
                md.append(f"- **Positive**: {pro if pro else 'N/A'}")
                md.append(f"- **Negative**: {con if con else 'N/A'}")
                md.append("")
        
        # (4) Non-financial factors summary and other plain-text sections
        elif isinstance(section.get("content"), str):
            md.append(section["content"])
        
        md.append("\n---\n")

    return "\n".join(md).strip()

# 6) Append detailed debate statements
def append_detailed_statements(md_text: str, task_outputs: list) -> str:
    md_text += "\n## 6. (Appendix) Detailed Debate Statements\n\n"
    for i, task_output in enumerate(task_outputs[:-1], 1):
        md_text += f"### Statement {i}: {task_output.agent}\n"
        md_text += f"{task_output.raw.strip()}\n\n"
    return md_text.strip()

# 7) Append web search results collected during the debate
def append_search_results(md_text: str, search_info: list) -> str:
    if not search_info:
        return md_text

    md_text += "\n\n## 7. (Appendix) Web Search Results Collected During Debate\n\n"

    for i, search_item in enumerate(search_info, 1):
        title = search_item.get('title', 'No title')
        url = search_item.get('url', '#')
        summary = search_item.get('summary', search_item.get('content', 'No content'))
        timestamp = search_item.get('timestamp', 'No timestamp')
        agent = search_item.get('agent', search_item.get('query', 'Unknown searcher'))

        # Display title as a markdown link when a URL is available
        if url and url != '#':
            md_text += f"### {i}. [{title}]({url})\n\n"
        else:
            md_text += f"### {i}. {title}\n\n"
        
        md_text += f"- **Searcher**: {agent}\n"
        md_text += f"- **Collected at**: {timestamp}\n"
        md_text += f"- **Summary**: {summary}\n\n"

        if url and url != '#':
            md_text += f"- **Source**: {url}\n\n"
        
        md_text += "---\n\n"
    
    return md_text.strip()

# Generate Markdown text and append statements and web search results
markdown_text = json_to_markdown(final_report)
markdown_text = append_detailed_statements(markdown_text, task_outputs)
markdown_text = append_search_results(markdown_text, collected_search_info)

# Save Markdown report
with open(markdown_path, "w", encoding="utf-8") as f:
    f.write(markdown_text)

print(f"✅ Markdown 보고서 저장 완료: {markdown_path}")

# Run pandoc to generate PDF
result = subprocess.run(
    [
        "pandoc", markdown_path,
        "--pdf-engine=xelatex",
        "-V", "mainfont=Helvetica",
        "-V", "geometry=margin=1in",
        "-o", pdf_path
    ],
    capture_output=True,
    text=True
)

# Print pandoc execution results
print("STDOUT:\n", result.stdout)
print("STDERR:\n", result.stderr)

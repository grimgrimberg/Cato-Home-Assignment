# RPA + Agentic AI Challenge: “The Daily Movers Assistant”

Cato Networks – Candidate Assignment Brief

## Business Story

Imagine you’re part of a dynamic investment research team. Each morning, executives and analysts start their day by asking:

_“Which companies are driving the market today, and what’s behind the movement?”_

Currently, this process is manual and slow. Analysts visit financial sites like Yahoo Finance to identify the top movers, read multiple articles to understand why a stock moved, and manually summarize their insights. By the time they share results, the market has already shifted.

Your mission is to automate this workflow using UiPath and agentic AI — designing a Daily Movers Assistant that runs daily, gathers, analyzes, and summarizes stock movements with recommendations.

## The Goal

Create a system that runs daily and automatically:  
1\. Retrieves the Top 20 market movers from https://finance.yahoo.com/markets/stocks/most-active/.  
2\. Enriches each stock with background context (news, earnings, sentiment).  
3\. Produces a summary table with AI-generated recommendations.  
4\. Displays results in one or more channels — Excel, email, or any application interface.  
5\. Includes an agent that performs reasoning and delivers explainable insights.

## Business Requirements

The system should run daily (or on-demand), collect and process top movers, and provide insights such as open/close prices, daily change, and earnings date. It should generate concise summaries and recommendations for each company and highlight positive and negative movers, the top recommended stock, and the one with the most potential.

## Agentic Component

The core of the challenge is the agent that performs reasoning and analysis. It can be built using either UiPath Coded Agents SDK (LangGraph) — extra points for creative use — or UiPath Agent Builder (or similar low-code approach). The agent should analyze, summarize, and recommend with clear reasoning.

## Output Channels

The system should deliver results through at least one of the following, with justification for your choice:

\- Excel report (analyst-friendly)  
\- Email summary (executive digest)  
\- Application interface (UiPath App, web app, or desktop app)  
<br/>Extra points for combining multiple channels with a clear rationale.

## Candidate Deliverables

A. System Deliverables  
1\. Automated process to retrieve and analyze top 20 movers.  
2\. Agentic layer that summarizes and recommends actions.  
3\. Output in one or more channels, with justification.  
4\. Highlights for top gainers, losers, and key recommendations.  
5\. Executable or project files that can run on a different machine.  
<br/>B. Documentation  
1\. Business Concept — problem, stakeholders, and output choice.  
2\. Technical Overview — architecture, reasoning logic, and setup steps.  
<br/>C. Packaging  
GitHub repo or ZIP with UiPath projects, agent/app exports, sample outputs, and documentation.

## Interview Presentation

In the interview, you’ll present:  
1\. Business scenario and value.  
2\. Architecture and design.  
3\. Agent reasoning and outputs.  
4\. System demo.  
5\. Challenges, limitations, and next steps.

## Evaluation Criteria

Business Understanding— clarity and business value.  
Solution Architecture— soundness and documentation.  
Agentic Reasoning— creativity and explainability.  
Output & Presentation— clarity and usability.  
Communication— ability to articulate and present.  
Bonus: LangGraph use, multi-channel design, Maestro integration

## Final Note

This challenge evaluates how you think, design, and connect automation with reasoning to deliver business value. There’s no single correct solution — creativity, structure, and clarity will stand out.

The solution shouldn’t be perfect, but it should provide us with the understanding of your capabilities and knowledge.
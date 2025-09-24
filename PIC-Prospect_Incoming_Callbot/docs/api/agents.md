# Agents API Reference

This document provides detailed API reference for the agent system components, including the LangGraph workflow, individual agents, and state management.

## Agent Graph API

### Main Graph Definition

**File**: `app/agents/agents_graph.py`

**Class**: `AgentGraph`

```python
class AgentGraph:
    def __init__(self, config: AgentGraphConfig):
        self.graph = StateGraph(PhoneConversationState)
        self.setup_agents()
        self.setup_transitions()

    async def execute_async(self, initial_state: PhoneConversationState) -> PhoneConversationState:
        """Execute the agent graph workflow"""
```

### State Model

**File**: `app/agents/phone_conversation_state_model.py`

```python
class PhoneConversationState(TypedDict):
    # Conversation metadata
    call_id: str
    caller_phone: str
    start_time: datetime
    current_phase: ConversationPhase

    # Conversation content
    conversation_history: List[ConversationTurn]
    current_user_input: str
    current_agent_response: str

    # Lead qualification
    prospect_info: ProspectInfo
    qualification_score: float
    qualification_complete: bool

    # Appointment scheduling
    appointment_preferences: AppointmentPreferences
    appointment_scheduled: Optional[AppointmentDetails]

    # External system data
    salesforce_lead_id: Optional[str]
    calendar_event_id: Optional[str]

    # Agent state
    current_agent: AgentType
    agent_context: Dict[str, Any]
    next_action: Optional[str]
```

### Graph Execution

```python
@graph.node("lead_agent")
async def execute_lead_agent_async(state: PhoneConversationState) -> PhoneConversationState:
    """Execute lead qualification agent"""
    agent = LeadAgent()
    return await agent.process_async(state)

@graph.node("calendar_agent")
async def execute_calendar_agent_async(state: PhoneConversationState) -> PhoneConversationState:
    """Execute calendar scheduling agent"""
    agent = CalendarAgent()
    return await agent.process_async(state)

@graph.node("salesforce_agent")
async def execute_salesforce_agent_async(state: PhoneConversationState) -> PhoneConversationState:
    """Execute Salesforce CRM agent"""
    agent = SalesforceAgent()
    return await agent.process_async(state)
```

### Conditional Routing

```python
def route_next_agent(state: PhoneConversationState) -> str:
    """Determine the next agent based on current state"""
    if not state["qualification_complete"]:
        return "lead_agent"
    elif state["qualification_score"] >= 7 and not state["appointment_scheduled"]:
        return "calendar_agent"
    elif state["appointment_scheduled"] and not state["salesforce_lead_id"]:
        return "salesforce_agent"
    else:
        return END
```

## Lead Agent API

### Class Definition

**File**: `app/agents/lead_agent.py`

```python
class LeadAgent:
    def __init__(self, config: LeadAgentConfig):
        self.config = config
        self.llm = create_llm_from_config(config.llm_config)

    async def process_async(self, state: PhoneConversationState) -> PhoneConversationState:
        """Main agent processing method"""

    async def qualify_prospect_async(self, state: PhoneConversationState) -> QualificationResult:
        """Conduct prospect qualification"""

    async def extract_prospect_info_async(self, conversation_text: str) -> ProspectInfo:
        """Extract prospect information from conversation"""

    async def calculate_qualification_score_async(self, prospect_info: ProspectInfo) -> float:
        """Calculate lead qualification score"""
```

### Qualification Scoring

```python
class QualificationCriteria:
    BUDGET_AVAILABLE = "budget_available"      # Weight: 3
    DECISION_MAKER = "decision_maker"          # Weight: 2
    TIMELINE_URGENT = "timeline_urgent"        # Weight: 2
    NEED_IDENTIFIED = "need_identified"        # Weight: 2
    COMPANY_SIZE = "company_size"              # Weight: 1

async def score_qualification_async(self, prospect_info: ProspectInfo) -> QualificationScore:
    """
    Calculate qualification score based on BANT criteria:
    - Budget: Does the prospect have budget available?
    - Authority: Is the contact a decision maker?
    - Need: Is there a clear business need?
    - Timeline: Is there urgency to make a decision?
    """
    score = 0
    criteria_met = {}

    # Budget assessment
    if prospect_info.budget_indicated:
        score += 3
        criteria_met[QualificationCriteria.BUDGET_AVAILABLE] = True

    # Authority assessment
    if prospect_info.job_title in DECISION_MAKER_TITLES:
        score += 2
        criteria_met[QualificationCriteria.DECISION_MAKER] = True

    # Need assessment
    if prospect_info.pain_points:
        score += 2
        criteria_met[QualificationCriteria.NEED_IDENTIFIED] = True

    # Timeline assessment
    if prospect_info.timeline and prospect_info.timeline <= 90:  # days
        score += 2
        criteria_met[QualificationCriteria.TIMELINE_URGENT] = True

    return QualificationScore(score=score, max_score=10, criteria_met=criteria_met)
```

### Prospect Information Extraction

```python
class ProspectInfo(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    pain_points: List[str] = []
    budget_indicated: bool = False
    timeline: Optional[int] = None  # days
    additional_notes: str = ""

async def extract_prospect_info_async(self, conversation_text: str) -> ProspectInfo:
    """Extract structured prospect information using LLM"""
    extraction_prompt = f"""
    Extract prospect information from this conversation:
    {conversation_text}

    Return JSON with the following structure:
    {{
        "name": "prospect name or null",
        "company": "company name or null",
        "job_title": "job title or null",
        "email": "email address or null",
        "industry": "industry or null",
        "pain_points": ["list", "of", "pain points"],
        "budget_indicated": true/false,
        "timeline": number of days or null
    }}
    """

    response = await self.llm.agenerate([extraction_prompt])
    return ProspectInfo.parse_raw(response.generations[0][0].text)
```

## Calendar Agent API

### Class Definition

**File**: `app/agents/calendar_agent.py`

```python
class CalendarAgent:
    def __init__(self, config: CalendarAgentConfig):
        self.config = config
        self.calendar_client = create_calendar_client()
        self.llm = create_llm_from_config(config.llm_config)

    async def process_async(self, state: PhoneConversationState) -> PhoneConversationState:
        """Main calendar agent processing"""

    async def check_availability_async(self, date_preferences: List[datetime]) -> List[TimeSlot]:
        """Check calendar availability for preferred dates"""

    async def schedule_appointment_async(self, appointment_request: AppointmentRequest) -> AppointmentResult:
        """Schedule a new appointment"""

    async def handle_scheduling_conflict_async(self, conflict: SchedulingConflict) -> ConflictResolution:
        """Handle scheduling conflicts"""
```

### Availability Checking

```python
class TimeSlot(BaseModel):
    start_time: datetime
    end_time: datetime
    available: bool
    conflict_reason: Optional[str] = None

async def find_available_slots_async(
    self,
    start_date: datetime,
    end_date: datetime,
    duration_minutes: int = 30,
    business_hours_only: bool = True
) -> List[TimeSlot]:
    """Find available time slots within date range"""

    # Get existing appointments
    existing_appointments = await self.calendar_client.get_events_async(start_date, end_date)

    # Generate potential time slots
    potential_slots = self._generate_time_slots(start_date, end_date, duration_minutes)

    # Check availability
    available_slots = []
    for slot in potential_slots:
        is_available = not any(
            self._slots_overlap(slot, appointment)
            for appointment in existing_appointments
        )

        available_slots.append(TimeSlot(
            start_time=slot.start_time,
            end_time=slot.end_time,
            available=is_available,
            conflict_reason=None if is_available else "Calendar conflict"
        ))

    return available_slots
```

### Appointment Scheduling

```python
class AppointmentRequest(BaseModel):
    prospect_info: ProspectInfo
    preferred_date: datetime
    duration_minutes: int = 30
    meeting_type: MeetingType = MeetingType.CONSULTATION
    location: Optional[str] = None
    notes: Optional[str] = None

class AppointmentResult(BaseModel):
    success: bool
    appointment_id: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    error_message: Optional[str] = None
    alternative_times: List[datetime] = []

async def create_appointment_async(self, request: AppointmentRequest) -> AppointmentResult:
    """Create calendar appointment"""
    try:
        # Check if requested time is available
        if not await self._is_time_available_async(request.preferred_date, request.duration_minutes):
            alternatives = await self._suggest_alternative_times_async(request.preferred_date)
            return AppointmentResult(
                success=False,
                error_message="Requested time not available",
                alternative_times=alternatives
            )

        # Create calendar event
        event_data = CalendarEvent(
            title=f"Consultation with {request.prospect_info.name}",
            start_time=request.preferred_date,
            end_time=request.preferred_date + timedelta(minutes=request.duration_minutes),
            attendees=[request.prospect_info.email] if request.prospect_info.email else [],
            description=f"Lead qualification call with {request.prospect_info.company}",
            location=request.location
        )

        event = await self.calendar_client.create_event_async(event_data)

        return AppointmentResult(
            success=True,
            appointment_id=event.id,
            scheduled_time=event.start_time
        )

    except Exception as e:
        logger.error(f"Failed to create appointment: {e}")
        return AppointmentResult(
            success=False,
            error_message=str(e)
        )
```

### Activity Logging

```python
class CallActivity(BaseModel):
    subject: str
    call_type: str = "Inbound"
    call_duration: int  # seconds
    call_result: str
    description: str
    activity_date: datetime

async def create_call_activity_async(self, lead_id: str, call_details: CallDetails) -> ActivityRecord:
    """Create call activity record"""

    activity_data = {
        'Subject': f"Inbound call from {call_details.caller_phone}",
        'WhoId': lead_id,
        'Type': 'Call',
        'Status': 'Completed',
        'Priority': 'Normal',
        'ActivityDate': call_details.call_date.date(),
        'Description': self._generate_call_summary(call_details),
        'CallDurationInSeconds': call_details.duration_seconds,
        'CallType': 'Inbound'
    }

    return await self.sf_client.create_task_async(activity_data)

def _generate_call_summary(self, call_details: CallDetails) -> str:
    """Generate AI summary of call"""
    summary_prompt = f"""
    Generate a concise business summary of this phone call:

    Duration: {call_details.duration_seconds} seconds
    Qualification Score: {call_details.qualification_score}/10
    Key Points: {call_details.key_points}
    Outcome: {call_details.outcome}

    Focus on business value and next steps.
    """

    return self.llm.generate([summary_prompt]).generations[0][0].text
```

## State Management API

### State Persistence

```python
class StateManager:
    async def save_state_async(self, call_id: str, state: PhoneConversationState) -> None:
        """Persist conversation state"""

    async def load_state_async(self, call_id: str) -> Optional[PhoneConversationState]:
        """Load conversation state"""

    async def update_state_async(self, call_id: str, updates: Dict[str, Any]) -> PhoneConversationState:
        """Update specific state fields"""
```

### State Transitions

```python
class StateTransition(BaseModel):
    from_agent: AgentType
    to_agent: AgentType
    trigger: str
    timestamp: datetime
    state_changes: Dict[str, Any]

async def transition_to_agent_async(
    self,
    state: PhoneConversationState,
    target_agent: AgentType,
    reason: str
) -> PhoneConversationState:
    """Transition to a different agent"""

    transition = StateTransition(
        from_agent=state["current_agent"],
        to_agent=target_agent,
        trigger=reason,
        timestamp=datetime.utcnow(),
        state_changes={}
    )

    # Update state
    state["current_agent"] = target_agent
    state["agent_context"]["last_transition"] = transition

    # Log transition
    logger.info(f"Agent transition: {transition.from_agent} -> {transition.to_agent} ({reason})")

    return state
```

This comprehensive API reference provides all the necessary information for working with the agent system, including state management, individual agent capabilities, and integration patterns.
using Microsoft.AspNetCore.Mvc;
using Studi.AI.Chatbot.Front.Services;

namespace Studi.AI.Chatbot.Front.Controller;

[ApiController]
[Route("[controller]")]
public class FrontendProxyController : ControllerBase
{
    public FrontendProxyController(ConversationService ConversationService)
    {
        _ConversationService = ConversationService;
    }

    private readonly ConversationService _ConversationService;

    [HttpGet("ping")]
    public string Ping()
    {
        return "pong";
    }
}

using Microsoft.AspNetCore.Mvc;
using PoAssistant.Front.Data;
using PoAssistant.Front.Services;
using System.Text;
using System.IO;
using PoAssistant.Front.Helpers;

namespace PoAssistant.Front.Controller;

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

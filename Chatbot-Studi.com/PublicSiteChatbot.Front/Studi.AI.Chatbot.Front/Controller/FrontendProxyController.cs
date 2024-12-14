using Microsoft.AspNetCore.Mvc;
using Studi.AI.Chatbot.Front.Services;

namespace Studi.AI.Chatbot.Front.Controller;

[ApiController]
[Route("[controller]")]
public class ProxyController : ControllerBase
{
    public ProxyController(ConversationService ConversationService)
    {
        _ConversationService = ConversationService;
    }

    private readonly ConversationService _ConversationService;

    //[HttpGet("get-ip")]
    //public IActionResult GetClientIp()
    //{
    //    var ipAddress = HttpContext.Connection.RemoteIpAddress?.ToString();
    //    return Ok(ipAddress);
    //}

    [HttpGet("ping")]
    public string Ping()
    {
        return "pong";
    }
}

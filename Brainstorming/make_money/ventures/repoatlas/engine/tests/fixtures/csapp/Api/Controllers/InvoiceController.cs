using Microsoft.AspNetCore.Mvc;
using Billing.Api.Services;

namespace Billing.Api.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class InvoiceController : ControllerBase
    {
        private readonly InvoiceService _service;

        public InvoiceController(InvoiceService service)
        {
            _service = service;
        }

        [HttpGet]
        public IActionResult List()
        {
            return Ok(_service.ListAll());
        }

        [HttpPost("retry/{id}")]
        public IActionResult Retry(int id)
        {
            return Ok(_service.Retry(id));
        }
    }
}

using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Studi.Api.Lms.Messenger.Application.Services.ConversationObjectService;
using Studi.Api.Lms.Messenger.Controllers.ConversationObject.Mapping;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.ConversationObject.ResponseModels;
using Studi.Api.Lms.Messenger.Utils.Middleware;
using Swashbuckle.AspNetCore.Annotations;
using System.Net;

namespace Studi.Api.Lms.Messenger.Controllers.ConversationObject;

/// <summary>
/// Controller for managing ConversationObjects and related operations.
/// </summary>
[ApiController]
[Route("v{version:apiVersion}/conversation-objects")]
[Authorize]
public class ConversationObjectController : ControllerBase
{
    private readonly IConversationObjectService _conversationObjectService;

    /// <summary>
    /// Initializes a new instance of the <see cref="ConversationObjectController"/> class.
    /// </summary>
    /// <param name="conversationObjectService">The conversation object service to be injected.</param>
    public ConversationObjectController(IConversationObjectService conversationObjectService)
    {
        _conversationObjectService = conversationObjectService;
    }

    /// <summary>
    /// Retrieves ConversationObjects associated with a specific internal service.
    /// </summary>
    /// <param name="internalServiceCode">The code of the internal service.</param>
    /// <returns>A collection of ConversationObjectResponseModel.</returns>
    [HttpGet("internal-services/{internalServiceCode}")]
    [ApiVersion("1")]
    [SwaggerOperation("Retrieves ConversationObjects associated with a specific internal service.")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(IEnumerable<ConversationObjectResponseModel>))]
    [SkipCheckParamsAgainstLmsToken]
    public async Task<IEnumerable<ConversationObjectResponseModel>> GetConversationObjectsAsync(string internalServiceCode)
    {
        var conversationObjects = await _conversationObjectService.GetConversationObjectsAsync(internalServiceCode);
        return conversationObjects.Select(co => co.ToResponseModel());
    }

    /// <summary>
    /// Retrieves ConversationSubObjects associated with a specific ConversationObject.
    /// </summary>
    /// <param name="conversationObjectCode">The code of the ConversationObject.</param>
    /// <returns>A collection of ConversationSubObjectResponseModel.</returns>
    [HttpGet("{conversationObjectCode}/conversation-sub-objects")]
    [ApiVersion("1")]
    [SwaggerOperation("Retrieves ConversationSubObjects associated with a specific ConversationObject.")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(IEnumerable<ConversationSubObjectResponseModel>))]
    [SkipCheckParamsAgainstLmsToken]
    public async Task<IEnumerable<ConversationSubObjectResponseModel>> GetConversationSubObjectsAsync(string conversationObjectCode)
    {
        var conversationSubObjects = await _conversationObjectService.GetConversationSubObjectsAsync(conversationObjectCode);
        return conversationSubObjects.Select(cso => cso.ToResponseModel());
    }

    /// <summary>
    /// Retrieves the list of internal services (support team).
    /// </summary>
    /// <returns>A collection of InternalServiceResponseModel.</returns>
    [HttpGet("internal-services")]
    [ApiVersion("1")]
    [SwaggerOperation("Retrieves the list of internal services.")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(IEnumerable<InternalServiceResponseModel>))]
    [SkipCheckParamsAgainstLmsToken]
    public async Task<IEnumerable<InternalServiceResponseModel>> GetInternalServicesAsync()
    {
        var internalServices = await _conversationObjectService.GetInternalServicesAsync();
        return internalServices.Select(intServ => intServ.ToResponseModel());
    }
}

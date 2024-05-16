using CsvHelper;
using CsvHelper.Configuration;
using MediatR;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.Localization;
using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Lms.User.Application.Interfaces;
using Studi.Api.Lms.User.Application.Services.Civility;
using Studi.Api.Lms.User.Application.Services.CustomWebResource;
using Studi.Api.Lms.User.Application.Mapping;
using Studi.Api.Lms.User.Application.Services.PaymentReliability;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Common.ITOs.Interfaces;
using Studi.Api.Lms.User.Common.RepositoriesInterfaces;
using Studi.Api.Lms.User.Domain.Commands;
using Studi.Api.Lms.User.Domain.UserAggregate.Commands;
using Studi.Api.Lms.User.Localization.Error.GeneratedClasses;
using Studi.Api.Tracking.Client;
using System.Globalization;

namespace Studi.Api.Lms.User.Application.Services
{
    [ScopedService(typeof(IUserProfileWritingService))]
    public class UserProfileWritingService : IUserProfileWritingService
    {
        private readonly IMediator _mediator;
        private readonly ICustomWebResourceService _customWebResource;
        private readonly ICivilityService _civilityService;
        private readonly IUserProfileQueryingService _userQueryService;
        private readonly ILogger<IUserProfileWritingService> _logger;
        private readonly ITrackingRestClient _trackingClient;
        private readonly IUserRepository _userRepository;


    /// <summary>
    /// Initialize dependencies, ensuring mediator, tracking client, logger, and user repository are set for handling user profile writing tasks.
    /// </summary>
    /// <param name="mediator">An instance of IMediator to handle mediator pattern operations between objects.</param>
    /// <param name="customWebResource">An instance of ICustomWebResourceService to manage custom web resources for the application.</param>
    /// <param name="civilityService">An instance of ICivilityService to handle user civility related operations.</param>
    /// <param name="userQueryService">An instance of IUserProfileQueryingService to query user profile information.</param>
    /// <param name="trackingClient">An instance of ITrackingRestClient to send tracking data to a specified endpoint.</param>
    /// <param name="logger">An instance of ILogger<IUserProfileWritingService> to log information and errors for the UserProfileWritingService.</param>
    /// <param name="userRepository">An instance of IUserRepository to handle user data persistence and retrieval.</param>
        public UserProfileWritingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserProfileQueryingService userQueryService, ITrackingRestClient trackingClient, ILogger<IUserProfileWritingService> logger, IUserRepository userRepository)
        {
            _mediator = mediator ?? throw new ArgumentNullException();
            _trackingClient = trackingClient;
            _logger = logger;
            _userRepository = userRepository;
        }


    /// <summary>
    /// Upload a CSV file that contains data related to payment reliability, and process the file to handle and extract the relevant information.
    /// </summary>
    /// <param name="file">The CSV file containing the payment reliability data to be uploaded.</param>
        public async Task UploadCsvFilePaymentReliabilityAsync(IFormFile file)
        {
            try
            {
                var configurationMapping = new CsvConfiguration(CultureInfo.InvariantCulture)
                {
                    HasHeaderRecord = true,
                    Delimiter = ";",
                };

                using (var streamReader = new StreamReader(file.OpenReadStream()))
                using (var csv = new CsvReader(streamReader, configurationMapping))
                {
                    csv.Context.RegisterClassMap<MappingCsvPaymentReliabilityMap>();
                    var records = csv.GetRecords<MappingCsvPaymentReliability>()
                                     .Select(q => new MappingCsvPaymentReliability
                                     {
                                         Name = q.Name,
                                         PaymentReliabilityCode = q.PaymentReliabilityCode.ToLower(),
                                         AccountId = q.AccountId,
                                         AccountId18Digits = q.AccountId18Digits
                                     })
                                     .Where(q => !string.IsNullOrEmpty(q.PaymentReliabilityCode))
                                     .ToList();

                    foreach (var record in records)
                    {
                        await UpdatePaymentReliabilityAsync(record.AccountId18Digits, record.PaymentReliabilityCode, true);
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error while processing csv upload");
            }
        }


    /// <summary>
    /// Update payment reliability for a user identified by a specified Salesforce ID.
    /// </summary>
    /// <param name="salesforceId">The unique identifier for the Salesforce record.</param>
    /// <param name="code">A specific code required by the endpoint to process the data.</param>
    /// <param name="isCsvUpload">A boolean flag indicating whether the data is being uploaded via CSV.</param>
        public async Task UpdatePaymentReliabilityAsync(string salesforceId, string code, bool isCsvUpload)
        {
            Guard.Against.NullOrEmpty(salesforceId, ErrorCode.Api.Lms.User.DataValidation.Common.SalesforceId.NullOrEmpty);

            var userId = await _userRepository.GetUserIdBySalesforceIdAsync(salesforceId);

            if (userId != 0)
            {
                var userReliability = await _userRepository.GetUserReliabilityByUserId(userId);
                string comments = GetCommentsFromCode(code, userReliability);

                await _userRepository.UpdatePaymentReliabilityAsync(userId, code);
                await SendTrackingAsync(userId, "Mise à jour de la situation de paiement", comments, "Salesforce");
            }
            else if (userId == 0 && !isCsvUpload)
            {
                Guard.Against.NegativeOrZero(userId, ErrorCode.Api.Lms.User.DataValidation.Command.PaymentReliability.UserIdNull);
            }
            else
            {
                _logger.LogWarning($"L'utilisateur avec l'id salesforce {salesforceId} donné n'a pas été mis à jour");
            }
        }


    /// <summary>
    /// Update the review date for a specified user's profile.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile review date is being updated. It is an integer value.</param>
    /// <param name="reviewDateUtc">The date and time (in UTC) of the review. This is an optional parameter; if not specified, it defaults to null.</param>
        public async Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDateUtc = null)
        {
            await _mediator.Send(new UserProfileReviewDateUpdateCommand(userId, reviewDateUtc));
        }


    /// <summary>
    /// Update the user's profile picture using the specified user identifier and file reference.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile picture is being updated.</param>
    /// <param name="fileGuid">The globally unique identifier (GUID) of the file representing the new profile picture.</param>
        public async Task UpdateProfilePictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserProfilePictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update the header picture of a specified user using a given file identifier.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose header picture is to be updated.</param>
    /// <param name="fileGuid">A GUID representing the unique identifier of the file containing the new header picture.</param>
        public async Task UpdateHeaderPictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserHeaderPictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update basic information for a specified user with provided LinkedIn URL and about me details.
    /// </summary>
    /// <param name="userId">The unique identifier for the user.</param>
    /// <param name="linkedInUrl">The LinkedIn profile URL of the user. This parameter is optional.</param>
    /// <param name="aboutMe">A brief description or information about the user. This parameter is optional.</param>
        public async Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe)
        {
            await _mediator.Send(new UserBasicInfoUpdateCommand(userId, linkedInUrl, aboutMe));
        }


    /// <summary>
    /// Update the visibility status of a user in the ranking for a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the tracking data is being sent.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="doesAppearInRanking">A boolean value indicating whether the user appears in the ranking or not.</param>
        public async Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking)
        {
            await _mediator.Send(new UserAppearsInRankingUpdateCommand(userId, schoolId, doesAppearInRanking));
        }


    /// <summary>
    /// Update the status of a user's appearance in the learner directory for a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose tracking data is being updated.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="doesAppearInLearnerDirectory">Boolean value indicating whether the user appears in the learner directory.</param>
    /// <param name="isOpenToCollaboration">Boolean value indicating whether the user is open to collaborate with others.</param>
        public async Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration)
        {
            await _mediator.Send(new UserAppearsInLearnerDirectoryUpdateCommand(userId, schoolId, doesAppearInLearnerDirectory, isOpenToCollaboration));
        }


    /// <summary>
    /// Update the actual location for a specified user, including the country code and timezone ID.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose location data is being updated.</param>
    /// <param name="countryCode">An optional string representing the ISO country code where the user is currently located. Can be null if the country code is unknown.</param>
    /// <param name="timezoneId">An optional string representing the time zone ID in which the user is located. Can be null if the timezone ID is unknown.</param>
        public async Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId)
        {
            await _mediator.Send(new UserActualLocationUpdateCommand(userId, countryCode, timezoneId));
        }


    /// <summary>
    /// Add a new professional experience entry for a specified user.
    /// </summary>
    /// <param name="professionalExperienceIto">An object containing all the details of the user's professional experience, which is to be sent to the endpoint for tracking.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being tracked and sent to the endpoint.</param>
    /// <returns>Returns a Task indicating the asynchronous operation status.</returns>
        public async Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            return await _mediator.Send(new UserProfessionalExperienceCreateCommand(professionalExperienceIto, userId));
        }


    /// <summary>
    /// Update the professional experience details for a specified user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience to be updated.</param>
    /// <param name="professionalExperienceIto">An object containing the updated details of the professional experience.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being updated.</param>
        public async Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceUpdateCommand(professionalExperienceId, professionalExperienceIto, userId));
        }


    /// <summary>
    /// Remove a user's professional experience based on provided identifiers.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience that is to be removed.</param>
    /// <param name="userId">The unique identifier of the user from whom the professional experience is being removed.</param>
        public async Task RemoveUserProfessionalExperienceAsync(int professionalExperienceId, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceDeleteCommand(professionalExperienceId, userId));
        }


    /// <summary>
    /// Replace the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user.</param>
    /// <param name="studyInfos">The study information to be sent to the specified endpoint.</param>
        public async Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos)
        {
            await _mediator.Send(new UserLatestStudyInformationsReplaceCommand(studyInfos, userId));
        }


    /// <summary>
    /// Update the notification registration details for a specified user and school, considering email and push subscription preferences.
    /// </summary>
    /// <param name="userId">The unique identifier for the user.</param>
    /// <param name="schoolId">The unique identifier for the school.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification to be updated.</param>
    /// <param name="isEmailSubscriptionActive">A nullable boolean indicating whether the email subscription is active.</param>
    /// <param name="isPushSubscriptionActive">A nullable boolean indicating whether the push subscription is active.</param>
        public async Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive)
        {
            await _mediator.Send(new UserNotificationRegistrationUpdateCommand(userId, schoolId, notificationTypeCode, isEmailSubscriptionActive, isPushSubscriptionActive));
        }


    /// <summary>
    /// Update the first connection date for a specified user using the provided connection date in UTC.
    /// 
    /// </summary>
    /// <param name="userId">The unique identifier of the user. This parameter is required and should be of type int.</param>
    /// <param name="connectionDateUtc">The optional date and time of the user's first connection in UTC. If not provided, it defaults to null and the current time will be used.</param>
        public async Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDateUtc = null)
        {
            await _mediator.Send(new UserFirstConnectionDateUpdateCommand(userId, connectionDateUtc));
        }


    /// <summary>
    /// Create a user profile by retrieving the civility information, generating a pseudo if not provided, and sending the necessary data through a command.
    /// </summary>
    /// <param name="civilityId">The unique identifier representing the user's civility status.</param>
    /// <param name="lastName">The user's last name.</param>
    /// <param name="firstName">The user's first name.</param>
    /// <param name="birthDate">The user's date of birth.</param>
    /// <param name="email">The user's email address.</param>
    /// <param name="pseudo">The user's pseudonym or nickname, which may be null.</param>
    /// <param name="isOfficial">A boolean value indicating whether the user is an official member.</param>
    /// <param name="isTester">A boolean value indicating whether the user is a tester.</param>
    /// <param name="maidenName">The user's maiden name, which may be null.</param>
    /// <param name="createBy">The identifier of the creator of the user profile.</param>
    /// <returns>Returns a task representing the asynchronous operation of creating a user profile.</returns>
        public async Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy)
        {
            var civility = _civilityService.GetCivility(civilityId);

            // If pseudo is null then generate it 
            pseudo ??= await _userQueryService.GeneratePseudoAsync(firstName, lastName);

            return await _mediator.Send(new UserProfileCreateCommand(civility!.Name, lastName, firstName, birthDate, email, pseudo!, isOfficial, isTester, _customWebResource.DefaultAvatarUrl, _customWebResource.DefaultHeaderProfileBackgroundUrl, maidenName, createBy));
        }


    /// <summary>
    /// Check if a given code is not null or empty.
    /// </summary>
    /// <param name="code">The code in string format that will be used to send tracking data.</param>
    /// <param name="userReliability">The IUserReliabilityIto object that provides user reliability information, used optionally in the tracking process.</param>
    /// <returns>Returns comments extracted from the given code.</returns>
        private string GetCommentsFromCode(string code, IUserReliabilityIto? userReliability)
        {
            string sentenceCode = string.Empty;

            if (!string.IsNullOrEmpty(code))
            {
                if (code == PaymentReliabilityCode.Echeance.ToLower())
                {
                    sentenceCode = "Ce client a une échéance impayée.";
                }
                else if (code == PaymentReliabilityCode.Contentieux.ToLower())
                {
                    sentenceCode = "Ce client est en contentieux.";
                }
            }

            if (userReliability is not null && string.IsNullOrEmpty(code))
            {
                return "Situation régularisée";
            }
            return $"{sentenceCode} Veuillez contacter le service Recouvrement.";
        }


    /// <summary>
    /// Send tracking data to a specified endpoint.
    /// </summary>
    /// <param name="userId">The unique identifier of the user. This parameter is an integer.</param>
    /// <param name="title">The title associated with the tracking data. This parameter is a string.</param>
    /// <param name="comments">Additional comments or notes related to the tracking data. This parameter is a string.</param>
    /// <param name="createBy">The name of the person or system who created the tracking data. This parameter is a string.</param>
        private async Task SendTrackingAsync(int userId, string title, string comments, string createBy)
        {
            try
            {
                var source = await _trackingClient.GetTrackingSourceByCodeAsync("INFORMATION");
                var subReason = await _trackingClient.GetTrackingSubReasonByCodeAsync("SUJET_COMPTABILITE");

                await _trackingClient.CreateTrackingAsync(new Tracking.Client.Models.BindingModels.UserTrackingCreateBM
                {
                    userId = userId,
                    sourceId = source.Id,
                    subReasonId = subReason.Id,
                    type = "sortant",
                    title = title,
                    comments = comments,
                    createdDate = StudiTime.Now,
                    createdBy = createBy
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error while processing tracking client request");
            }
        }
    }
}
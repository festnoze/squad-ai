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
    /// Initialize the service with provided mediator, tracking client, logger, and user repository.
    /// </summary>
    /// <param name="mediator">Mediator object for handling and dispatching messages or requests within the application.</param>
    /// <param name="customWebResource">Service to manage custom web resources, potentially for loading configurations or resources.</param>
    /// <param name="civilityService">Service handling operations related to civilities, such as titles or salutations.</param>
    /// <param name="userQueryService">Service for querying user profiles, facilitating access to user information.</param>
    /// <param name="trackingClient">Client to send tracking information to a specified endpoint.</param>
    /// <param name="logger">Logging service for recording runtime information, errors, and actions related to the user profile writing service.</param>
    /// <param name="userRepository">Repository interface for performing CRUD operations on user data within the database.</param>
        public UserProfileWritingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserProfileQueryingService userQueryService, ITrackingRestClient trackingClient, ILogger<IUserProfileWritingService> logger, IUserRepository userRepository)
        {
            _mediator = mediator ?? throw new ArgumentNullException();
            _trackingClient = trackingClient;
            _logger = logger;
            _userRepository = userRepository;
        }


    /// <summary>
    /// Analyze the content of a CSV file related to payment reliability, ensure data validation, and upload it to the server logging any issues encountered.
    /// </summary>
    /// <param name="file">The CSV file containing the tracking information that needs to be uploaded.</param>
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
    /// Update the reliability status of a payment based on the provided Salesforce ID, ensuring the ID is not null or empty and retrieving the corresponding user ID for further validation.
    /// </summary>
    /// <param name="salesforceId">The unique identifier associated with the Salesforce record. This parameter is used to identify the specific record within Salesforce to update.</param>
    /// <param name="code">The code associated with the payment reliability update. This parameter specifies the type or category of the update being sent.</param>
    /// <param name="isCsvUpload">A boolean value that indicates whether the data is being uploaded in CSV format. True if uploading CSV data, otherwise false.</param>
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
    /// Update the review date of a user's profile to a specified timestamp.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the profile review date is to be updated. This parameter is mandatory.</param>
    /// <param name="reviewDateUtc">The date and time of the review in UTC. This parameter is optional and defaults to null if not provided.</param>
        public async Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDateUtc = null)
        {
            await _mediator.Send(new UserProfileReviewDateUpdateCommand(userId, reviewDateUtc));
        }


    /// <summary>
    /// Update the profile picture for a specified user using the provided file identifier.
    /// </summary>
    /// <param name="userId">An integer representing the unique user identifier for whom the profile picture is being updated.</param>
    /// <param name="fileGuid">A globally unique identifier (GUID) representing the file associated with the user's profile picture.</param>
        public async Task UpdateProfilePictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserProfilePictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update the header picture for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose header picture is to be updated.</param>
    /// <param name="fileGuid">The unique identifier (GUID) of the file representing the new header picture.</param>
        public async Task UpdateHeaderPictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserHeaderPictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update basic information for a specified user based on given parameters.
    /// </summary>
    /// <param name="userId">The unique identifier of the user. This is an integer value.</param>
    /// <param name="linkedInUrl">The LinkedIn profile URL of the user. This is a nullable string value.</param>
    /// <param name="aboutMe">A brief description or bio about the user. This is a nullable string value.</param>
        public async Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe)
        {
            await _mediator.Send(new UserBasicInfoUpdateCommand(userId, linkedInUrl, aboutMe));
        }


    /// <summary>
    /// Update user ranking status based on provided user ID, school ID, and appearance indicator.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This is used to specify the user whose tracking information is being updated.</param>
    /// <param name="schoolId">The unique identifier for the school. This parameter helps in identifying the school associated with the user.</param>
    /// <param name="doesAppearInRanking">A boolean value indicating whether the user appears in the ranking. True if the user appears in the ranking, false otherwise.</param>
        public async Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking)
        {
            await _mediator.Send(new UserAppearsInRankingUpdateCommand(userId, schoolId, doesAppearInRanking));
        }


    /// <summary>
    /// Update the user's appearance in the learner directory based on specified parameters.
    /// </summary>
    /// <param name="userId">The unique identifier for the user.</param>
    /// <param name="schoolId">The unique identifier for the school.</param>
    /// <param name="doesAppearInLearnerDirectory">A boolean flag indicating whether the user should appear in the learner directory.</param>
    /// <param name="isOpenToCollaboration">A boolean flag indicating whether the user is open to collaboration.</param>
        public async Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration)
        {
            await _mediator.Send(new UserAppearsInLearnerDirectoryUpdateCommand(userId, schoolId, doesAppearInLearnerDirectory, isOpenToCollaboration));
        }


    /// <summary>
    /// Update the actual location for a specified user, including country and timezone details.
    /// </summary>
    /// <param name="userId">The identifier for the user. This value is required to specify which user's location is being updated.</param>
    /// <param name="countryCode">An optional parameter representing the country code. This can be used to tailor the location update based on regional settings.</param>
    /// <param name="timezoneId">An optional parameter representing the timezone ID. This assists in adjusting the tracking information to the correct time zone context.</param>
        public async Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId)
        {
            await _mediator.Send(new UserActualLocationUpdateCommand(userId, countryCode, timezoneId));
        }


    /// <summary>
    /// Add a professional experience for a specified user using a command to handle the operation.
    /// </summary>
    /// <param name="professionalExperienceIto">An object that contains the professional experience details of the user, including fields like company, role, duration, and other relevant information.</param>
    /// <param name="userId">The unique identifier of the user to whom the professional experience details will be associated.</param>
    /// <returns>Returns a task indicating the operation's success status.</returns>
        public async Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            return await _mediator.Send(new UserProfessionalExperienceCreateCommand(professionalExperienceIto, userId));
        }


    /// <summary>
    /// Update a user's professional experience.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience entry that needs to be updated.</param>
    /// <param name="professionalExperienceIto">An object containing the details and information of the professional experience to be updated.</param>
    /// <param name="userId">The unique identifier for the user whose professional experience is being updated.</param>
        public async Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceUpdateCommand(professionalExperienceId, professionalExperienceIto, userId));
        }


    /// <summary>
    /// Delete a specified user's professional experience by providing the professional experience ID and user ID.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience to be removed.</param>
    /// <param name="userId">The unique identifier for the user whose professional experience is to be removed.</param>
        public async Task RemoveUserProfessionalExperienceAsync(int professionalExperienceId, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceDeleteCommand(professionalExperienceId, userId));
        }


    /// <summary>
    /// Update the most recent study information for a specific user.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user.</param>
    /// <param name="studyInfos">An object of type StudyIto containing detailed study information relevant to the user.</param>
        public async Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos)
        {
            await _mediator.Send(new UserLatestStudyInformationsReplaceCommand(studyInfos, userId));
        }


    /// <summary>
    /// Update the notification registration settings for a specified user based on user ID, school ID, notification type, and subscription status for email and push notifications.
    /// </summary>
    /// <param name="userId">The unique identifier for the user for whom the notification settings are being updated.</param>
    /// <param name="schoolId">The identifier for the school associated with the user.</param>
    /// <param name="notificationTypeCode">A code that specifies the type of notification to be tracked and updated.</param>
    /// <param name="isEmailSubscriptionActive">Indicates whether the email subscription for notifications is active. This is an optional parameter.</param>
    /// <param name="isPushSubscriptionActive">Indicates whether the push subscription for notifications is active. This is an optional parameter.</param>
        public async Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive)
        {
            await _mediator.Send(new UserNotificationRegistrationUpdateCommand(userId, schoolId, notificationTypeCode, isEmailSubscriptionActive, isPushSubscriptionActive));
        }


    /// <summary>
    /// Update the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose connection date is being updated.</param>
    /// <param name="connectionDateUtc">An optional DateTime value representing the UTC date and time of the user's first connection. If not provided, defaults to null.</param>
        public async Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDateUtc = null)
        {
            await _mediator.Send(new UserFirstConnectionDateUpdateCommand(userId, connectionDateUtc));
        }


    /// <summary>
    /// Create a user profile with specified personal and optional details, ensuring pseudo generation if not provided.
    /// </summary>
    /// <param name="civilityId">A unique identifier representing the civility (e.g., Mr., Mrs., Ms., etc.) of the user.</param>
    /// <param name="lastName">The last name of the user.</param>
    /// <param name="firstName">The first name of the user.</param>
    /// <param name="birthDate">The birth date of the user.</param>
    /// <param name="email">The user's email address.</param>
    /// <param name="pseudo">The user's optional pseudonym or nickname. Can be null.</param>
    /// <param name="isOfficial">A boolean indicating if the profile is official.</param>
    /// <param name="isTester">A boolean indicating if the user is a beta tester.</param>
    /// <param name="maidenName">The maiden name of the user, if applicable. Can be null.</param>
    /// <param name="createBy">The identifier of the entity or user who created the profile.</param>
    /// <returns>Returns the newly created user profile.</returns>
        public async Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy)
        {
            var civility = _civilityService.GetCivility(civilityId);

            // If pseudo is null then generate it 
            pseudo ??= await _userQueryService.GeneratePseudoAsync(firstName, lastName);

            return await _mediator.Send(new UserProfileCreateCommand(civility!.Name, lastName, firstName, birthDate, email, pseudo!, isOfficial, isTester, _customWebResource.DefaultAvatarUrl, _customWebResource.DefaultHeaderProfileBackgroundUrl, maidenName, createBy));
        }


    /// <summary>
    /// Retrieve comments embedded within a code snippet if the provided code is not null or empty.
    /// </summary>
    /// <param name="code">The code string representing the tracking information to be sent to the specified endpoint.</param>
    /// <param name="userReliability">An optional IUserReliability object that provides reliability information about the user associated with the tracking information.</param>
    /// <returns>Returns the extracted comments from a non-null or non-empty code snippet.</returns>
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
    /// Send tracking information to a specified endpoint based on certain parameters.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier for the user.</param>
    /// <param name="title">A string specifying the title associated with the tracking information.</param>
    /// <param name="comments">A string containing any additional comments or notes regarding the tracking information.</param>
    /// <param name="createBy">A string indicating the creator or author of the tracking information.</param>
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
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
    /// Initialize the necessary components for managing user profile writing operations.
    /// </summary>
    /// <param name="mediator">An IMediator instance for handling and dispatching commands and queries between different components within the service.</param>
    /// <param name="customWebResource">An ICustomWebResourceService instance used for managing custom web resources required for user profiles.</param>
    /// <param name="civilityService">An ICivilityService instance that handles user civility and title-related operations.</param>
    /// <param name="userQueryService">An IUserProfileQueryingService instance for querying user profile information from the data source.</param>
    /// <param name="trackingClient">An ITrackingRestClient instance used for interacting with the tracking service for posting and retrieving tracking details accurately.</param>
    /// <param name="logger">An ILogger<IUserProfileWritingService> instance for logging operations and errors within the UserProfileWritingService.</param>
    /// <param name="userRepository">An IUserRepository instance for accessing and manipulating user data within the repository.</param>
        public UserProfileWritingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserProfileQueryingService userQueryService, ITrackingRestClient trackingClient, ILogger<IUserProfileWritingService> logger, IUserRepository userRepository)
        {
            _mediator = mediator ?? throw new ArgumentNullException();
            _trackingClient = trackingClient;
            _logger = logger;
            _userRepository = userRepository;
        }


    /// <summary>
    /// Upload and process a CSV file to evaluate payment reliability.
    /// </summary>
    /// <param name="file">The CSV file containing tracking details to be uploaded. This file will be processed to extract data which will then be posted to the specified destination, ensuring accurate data conveyance and proper error handling.</param>
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
    /// Update the reliability status of a payment based on the provided Salesforce ID.
    /// </summary>
    /// <param name="salesforceId">The unique identifier for the Salesforce record, used to obtain tracking details from the provided Salesforce source.</param>
    /// <param name="code">A code that specifies the type or category of tracking details being processed, ensuring they are correctly matched with the appropriate records.</param>
    /// <param name="isCsvUpload">A boolean flag indicating whether the data is being uploaded in CSV format, enabling specific handling and processing routines for CSV uploads.</param>
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
    /// Update the review date of a specific user's profile based on provided information.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile review date is being updated.</param>
    /// <param name="reviewDateUtc">The date and time (in UTC) for the review of the user's profile; defaults to null if not provided.</param>
        public async Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDateUtc = null)
        {
            await _mediator.Send(new UserProfileReviewDateUpdateCommand(userId, reviewDateUtc));
        }


    /// <summary>
    /// Update the profile picture for a specified user.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose profile picture is being updated.</param>
    /// <param name="fileGuid">A Guid representing the unique identifier of the file that contains the new profile picture.</param>
        public async Task UpdateProfilePictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserProfilePictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update the header picture for a specified user using the provided file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier of the user who is updating the header picture. It ensures the request is associated with the correct user.</param>
    /// <param name="fileGuid">The globally unique identifier of the file representing the new header picture. This ID ensures the correct file is being referenced for the update.</param>
        public async Task UpdateHeaderPictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserHeaderPictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update basic information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This is an integer value that specifies which user's information is being updated.</param>
    /// <param name="linkedInUrl">The LinkedIn URL of the user. This is an optional string that can be null, and it represents the user's LinkedIn profile link.</param>
    /// <param name="aboutMe">A brief description about the user. This is an optional string that can be null, providing additional information or a personal summary about the user.</param>
        public async Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe)
        {
            await _mediator.Send(new UserBasicInfoUpdateCommand(userId, linkedInUrl, aboutMe));
        }


    /// <summary>
    /// Update the user's ranking appearance status based on the provided identifiers.
    /// </summary>
    /// <param name="userId">The unique identifier for the user, used to track user-specific data and ensure proper authorization.</param>
    /// <param name="schoolId">The unique identifier for the school, used to fetch and associate school-specific details.</param>
    /// <param name="doesAppearInRanking">A boolean flag indicating whether the user should appear in the ranking. This determines if the ranking data should be updated accordingly.</param>
        public async Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking)
        {
            await _mediator.Send(new UserAppearsInRankingUpdateCommand(userId, schoolId, doesAppearInRanking));
        }


    /// <summary>
    /// Update the status of a user's appearance in the learner directory, including their openness to collaboration, based on specified user and school identifiers.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom tracking details are being updated.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="doesAppearInLearnerDirectory">Indicates whether the user appears in the learner directory.</param>
    /// <param name="isOpenToCollaboration">Indicates whether the user is open to collaboration with other learners.</param>
        public async Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration)
        {
            await _mediator.Send(new UserAppearsInLearnerDirectoryUpdateCommand(userId, schoolId, doesAppearInLearnerDirectory, isOpenToCollaboration));
        }


    /// <summary>
    /// Update the actual location of a specified user by sending a command with the user's ID, country code, and timezone ID.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user for whom the location is being updated. This parameter is mandatory.</param>
    /// <param name="countryCode">An optional string indicating the ISO 3166-1 alpha-2 country code relevant to the user's location. This parameter is optional and may be null.</param>
    /// <param name="timezoneId">An optional string representing the IANA time zone identifier associated with the user's location. This parameter is optional and may be null.</param>
        public async Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId)
        {
            await _mediator.Send(new UserActualLocationUpdateCommand(userId, countryCode, timezoneId));
        }


    /// <summary>
    /// Add a new professional experience record for a specified user.
    /// </summary>
    /// <param name="professionalExperienceIto">An input object containing professional experience details to be added. The object should encapsulate relevant information such as job titles, employment dates, and any other pertinent details about the user's professional background.</param>
    /// <param name="userId">The unique identifier for the user to whom the professional experience details belong. This integer is used to ensure that the correct user's information is updated.</param>
    /// <returns>Returns a task representing the asynchronous add operation.</returns>
        public async Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            return await _mediator.Send(new UserProfessionalExperienceCreateCommand(professionalExperienceIto, userId));
        }


    /// <summary>
    /// Update the professional experience details for a specified user.
    /// </summary>
    /// <param name="professionalExperienceId">Unique identifier for the professional experience that needs to be updated.</param>
    /// <param name="professionalExperienceIto">Data transfer object containing the updated details of the professional experience.</param>
    /// <param name="userId">Unique identifier for the user whose professional experience is being updated.</param>
        public async Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceUpdateCommand(professionalExperienceId, professionalExperienceIto, userId));
        }


    /// <summary>
    /// Remove a specified professional experience for a user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience entry that needs to be removed.</param>
    /// <param name="userId">The unique identifier for the user whose professional experience entry needs to be removed.</param>
        public async Task RemoveUserProfessionalExperienceAsync(int professionalExperienceId, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceDeleteCommand(professionalExperienceId, userId));
        }


    /// <summary>
    /// Update the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">The identifier for the user. This is used to associate the provided study details with a specific user account.</param>
    /// <param name="studyInfos">The information about the study that needs to be posted. It contains all relevant details that will be used in tracking and data updates.</param>
        public async Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos)
        {
            await _mediator.Send(new UserLatestStudyInformationsReplaceCommand(studyInfos, userId));
        }


    /// <summary>
    /// Update a user's notification registration information based on specified parameters, including user ID, school ID, notification type, and subscription statuses for email and push notifications.
    /// </summary>
    /// <param name="userId">The unique identifier of the user.</param>
    /// <param name="schoolId">The unique identifier of the school.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification to be updated.</param>
    /// <param name="isEmailSubscriptionActive">Indicates whether the email subscription is currently active. This can be null if the status is not applicable.</param>
    /// <param name="isPushSubscriptionActive">Indicates whether the push subscription is currently active. This can be null if the status is not applicable.</param>
        public async Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive)
        {
            await _mediator.Send(new UserNotificationRegistrationUpdateCommand(userId, schoolId, notificationTypeCode, isEmailSubscriptionActive, isPushSubscriptionActive));
        }


    /// <summary>
    /// Update the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose first connection date is being updated. This integer is crucial as it determines which user's data will be tracked and updated.</param>
    /// <param name="connectionDateUtc">The optional date and time in UTC of the user's connection. If provided, this DateTime value will be used as the connection date; otherwise, the connection date will be set to a default value. This parameter is nullable.</param>
        public async Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDateUtc = null)
        {
            await _mediator.Send(new UserFirstConnectionDateUpdateCommand(userId, connectionDateUtc));
        }


    /// <summary>
    /// Create a user profile using provided information and default values when necessary, while ensuring civility and generating a pseudo if not given.
    /// </summary>
    /// <param name="civilityId">An integer representing the civility or title of the user (e.g., Mr., Mrs., etc.).</param>
    /// <param name="lastName">The last name or surname of the user.</param>
    /// <param name="firstName">The first name or given name of the user.</param>
    /// <param name="birthDate">The birth date of the user in a DateOnly format.</param>
    /// <param name="email">The email address of the user.</param>
    /// <param name="pseudo">An optional pseudonym or nickname for the user, if available.</param>
    /// <param name="isOfficial">A boolean value indicating whether the user profile is marked as official.</param>
    /// <param name="isTester">A boolean value indicating whether the user is a tester.</param>
    /// <param name="maidenName">An optional maiden name of the user, if applicable.</param>
    /// <param name="createBy">The identifier for the entity that created the user profile.</param>
    /// <returns>Returns a Task<UserProfile> containing newly created user profile details.</returns>
        public async Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy)
        {
            var civility = _civilityService.GetCivility(civilityId);

            // If pseudo is null then generate it 
            pseudo ??= await _userQueryService.GeneratePseudoAsync(firstName, lastName);

            return await _mediator.Send(new UserProfileCreateCommand(civility!.Name, lastName, firstName, birthDate, email, pseudo!, isOfficial, isTester, _customWebResource.DefaultAvatarUrl, _customWebResource.DefaultHeaderProfileBackgroundUrl, maidenName, createBy));
        }


    /// <summary>
    /// Retrieve comments associated with a given code snippet.
    /// </summary>
    /// <param name="code">The code string used to identify the specific tracking details to be retrieved and processed.</param>
    /// <param name="userReliability">An optional user reliability interface instance to ensure the accuracy and proper handling of data during the process.</param>
    /// <returns>Returns the comments extracted from the provided code snippet.</returns>
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
    /// Get tracking details from a provided source and post them to a specified destination ensuring data is conveyed accurately and handled properly in case of errors.
    /// </summary>
    /// <param name="userId">The unique identifier of the user initiating the SendTrackingAsync method.</param>
    /// <param name="title">The title of the tracking request, used to help categorize and identify the tracking data.</param>
    /// <param name="comments">Additional comments or notes that provide context or additional information about the tracking request.</param>
    /// <param name="createBy">The identifier of the entity or user who created the tracking entry, useful for auditing and tracking changes.</param>
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
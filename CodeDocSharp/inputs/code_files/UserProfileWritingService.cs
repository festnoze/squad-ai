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
    /// Initialize the service by assigning the provided mediator, tracking client, logger, and user repository, ensuring the mediator is not null.
    /// </summary>
    /// <param name="mediator">Facilitate communication between different parts of the application.</param>
    /// <param name="customWebResource">Handle custom web resource operations.</param>
    /// <param name="civilityService">Manage operations related to user civility.</param>
    /// <param name="userQueryService">Query user profiles and retrieve user-related information.</param>
    /// <param name="trackingClient">Send tracking data to the external tracking service.</param>
    /// <param name="logger">Log information and errors related to the user profile writing service.</param>
    /// <param name="userRepository">Interact with the database to perform operations on user data.</param>
        public UserProfileWritingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserProfileQueryingService userQueryService, ITrackingRestClient trackingClient, ILogger<IUserProfileWritingService> logger, IUserRepository userRepository)
        {
            _mediator = mediator ?? throw new ArgumentNullException();
            _trackingClient = trackingClient;
            _logger = logger;
            _userRepository = userRepository;
        }


    /// <summary>
    /// Upload the contents of a CSV file containing payment reliability data to a designated storage or processing system.
    /// </summary>
    /// <param name="file">The IFormFile representing the CSV file to be uploaded</param>
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
    /// Update the payment reliability for a given user based on their Salesforce ID.
    /// </summary>
    /// <param name="salesforceId">The Salesforce identifier used to associate the payment reliability update with the correct record in Salesforce.</param>
    /// <param name="code">A unique code representing the specific operation or transaction for which the payment reliability is being updated.</param>
    /// <param name="isCsvUpload">Indicates whether the payment reliability update is being uploaded via a CSV file.</param>
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
    /// Update the review date of the user profile with the specified user ID and UTC review date.
    /// </summary>
    /// <param name="userId">The unique identifier of the user to be analyzed or updated.</param>
    /// <param name="reviewDateUtc">The date and time of the review in UTC. If not provided, defaults to null.</param>
        public async Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDateUtc = null)
        {
            await _mediator.Send(new UserProfileReviewDateUpdateCommand(userId, reviewDateUtc));
        }


    /// <summary>
    /// Update the profile picture for a specified user using the provided file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile picture is to be updated.</param>
    /// <param name="fileGuid">The unique identifier of the file that will be used to update the user's profile picture.</param>
        public async Task UpdateProfilePictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserProfilePictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update the header picture for a specified user using a unique file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier for a user to update the header picture.</param>
    /// <param name="fileGuid">The unique identifier for the file representing the new header picture.</param>
        public async Task UpdateHeaderPictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserHeaderPictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update basic information for a specified user by sending a command with user ID, LinkedIn URL, and about me details.
    /// </summary>
    /// <param name="userId">The unique identifier for a user.</param>
    /// <param name="linkedInUrl">The optional LinkedIn profile URL for the user.</param>
    /// <param name="aboutMe">The optional personal information or biography for the user.</param>
        public async Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe)
        {
            await _mediator.Send(new UserBasicInfoUpdateCommand(userId, linkedInUrl, aboutMe));
        }


    /// <summary>
    /// Update a user's ranking appearance status based on specified conditions.
    /// </summary>
    /// <param name="userId">The unique identifier of a user.</param>
    /// <param name="schoolId">The unique identifier of a school.</param>
    /// <param name="doesAppearInRanking">A boolean value indicating whether it appears in the ranking.</param>
        public async Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking)
        {
            await _mediator.Send(new UserAppearsInRankingUpdateCommand(userId, schoolId, doesAppearInRanking));
        }


    /// <summary>
    /// Update the learner directory status for a specified user within a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user.</param>
    /// <param name="schoolId">The unique identifier of the school.</param>
    /// <param name="doesAppearInLearnerDirectory">A boolean value indicating whether the user appears in the learner directory.</param>
    /// <param name="isOpenToCollaboration">A boolean value indicating whether the user is open to collaboration.</param>
        public async Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration)
        {
            await _mediator.Send(new UserAppearsInLearnerDirectoryUpdateCommand(userId, schoolId, doesAppearInLearnerDirectory, isOpenToCollaboration));
        }


    /// <summary>
    /// Update the actual location of a specified user with new country and timezone data.
    /// </summary>
    /// <param name="userId">The identifier for the user for whom the location is being updated.</param>
    /// <param name="countryCode">The code representing the user's country, which is optional.</param>
    /// <param name="timezoneId">The identifier for the user's timezone, which is optional.</param>
        public async Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId)
        {
            await _mediator.Send(new UserActualLocationUpdateCommand(userId, countryCode, timezoneId));
        }


    /// <summary>
    /// Add a professional experience entry for a specified user.
    /// </summary>
    /// <param name="professionalExperienceIto">The professional experience information object that holds the details of the user's professional experience.</param>
    /// <param name="userId">The unique identifier of the user to whom the professional experience is being added.</param>
    /// <returns>Returns a task indicating the completion of the professional experience addition.</returns>
        public async Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            return await _mediator.Send(new UserProfessionalExperienceCreateCommand(professionalExperienceIto, userId));
        }


    /// <summary>
    /// Update professional experience details for a specified user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience being updated.</param>
    /// <param name="professionalExperienceIto">The data transfer object containing the updated details of the professional experience.</param>
    /// <param name="userId">The unique identifier for the user whose professional experience is being updated.</param>
        public async Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceUpdateCommand(professionalExperienceId, professionalExperienceIto, userId));
        }


    /// <summary>
    /// Remove a specified professional experience for a given user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience record to be removed.</param>
    /// <param name="userId">The unique identifier of the user associated with the professional experience.</param>
        public async Task RemoveUserProfessionalExperienceAsync(int professionalExperienceId, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceDeleteCommand(professionalExperienceId, userId));
        }


    /// <summary>
    /// Update the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user.</param>
    /// <param name="studyInfos">An object of type StudyIto containing the information related to the study.</param>
        public async Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos)
        {
            await _mediator.Send(new UserLatestStudyInformationsReplaceCommand(studyInfos, userId));
        }


    /// <summary>
    /// Update notification registration details for a user, considering their school ID, notification type, and preferences for email and push subscriptions.
    /// </summary>
    /// <param name="userId">The identifier of the user</param>
    /// <param name="schoolId">The identifier of the school</param>
    /// <param name="notificationTypeCode">The code representing the type of notification</param>
    /// <param name="isEmailSubscriptionActive">Indicates whether the email subscription is active</param>
    /// <param name="isPushSubscriptionActive">Indicates whether the push subscription is active</param>
        public async Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive)
        {
            await _mediator.Send(new UserNotificationRegistrationUpdateCommand(userId, schoolId, notificationTypeCode, isEmailSubscriptionActive, isPushSubscriptionActive));
        }


    /// <summary>
    /// Update the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user</param>
    /// <param name="connectionDateUtc">The optional UTC date and time of the user's connection; defaults to null if not provided</param>
        public async Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDateUtc = null)
        {
            await _mediator.Send(new UserFirstConnectionDateUpdateCommand(userId, connectionDateUtc));
        }


    /// <summary>
    /// Create a new user profile with generated pseudo if not provided, including personal details, official status, tester status, and default resources.
    /// </summary>
    /// <param name="civilityId">The unique identifier representing the individual's civility title.</param>
    /// <param name="lastName">The surname of the user.</param>
    /// <param name="firstName">The given name of the user.</param>
    /// <param name="birthDate">The birth date of the user.</param>
    /// <param name="email">The email address of the user.</param>
    /// <param name="pseudo">The optional pseudonym of the user.</param>
    /// <param name="isOfficial">Determines if the user is an official member.</param>
    /// <param name="isTester">Determines if the user is a tester.</param>
    /// <param name="maidenName">The optional maiden name of the user.</param>
    /// <param name="createBy">The identifier of the entity that created the user profile.</param>
    /// <returns>Returns a Task containing the newly created user profile object.</returns>
        public async Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy)
        {
            var civility = _civilityService.GetCivility(civilityId);

            // If pseudo is null then generate it 
            pseudo ??= await _userQueryService.GeneratePseudoAsync(firstName, lastName);

            return await _mediator.Send(new UserProfileCreateCommand(civility!.Name, lastName, firstName, birthDate, email, pseudo!, isOfficial, isTester, _customWebResource.DefaultAvatarUrl, _customWebResource.DefaultHeaderProfileBackgroundUrl, maidenName, createBy));
        }


    /// <summary>
    /// Get comments from a provided code string. Ensure the code string is not empty or null.
    /// </summary>
    /// <param name="code">The code that will be analyzed to summarize its functional purpose and behavior.</param>
    /// <param name="userReliability">An optional user reliability interface used to evaluate the trustworthiness of the user related to the code being analyzed.</param>
    /// <returns>Returns extracted comments from the provided code string.</returns>
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
    /// Send information about user activity to a tracking system.
    /// </summary>
    /// <param name="userId">The unique identifier of the user.</param>
    /// <param name="title">The title related to the tracking operation.</param>
    /// <param name="comments">The comments or remarks regarding the tracking operation.</param>
    /// <param name="createBy">The user who created the tracking entry.</param>
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
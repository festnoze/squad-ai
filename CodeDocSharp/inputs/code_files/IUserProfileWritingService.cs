using Microsoft.AspNetCore.Http;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileWritingService
    {

    /// <summary>
    /// Update the reliability status of a payment based on the provided Salesforce ID.
    /// </summary>
    /// <param name="salesforceId">The unique identifier for the Salesforce record, used to obtain tracking details from the provided Salesforce source.</param>
    /// <param name="code">A code that specifies the type or category of tracking details being processed, ensuring they are correctly matched with the appropriate records.</param>
    /// <param name="isCsvUpload">A boolean flag indicating whether the data is being uploaded in CSV format, enabling specific handling and processing routines for CSV uploads.</param>
        Task UpdatePaymentReliabilityAsync(string salesforceId, string code, bool isCsvUpload);

    /// <summary>
    /// Upload and process a CSV file to evaluate payment reliability.
    /// </summary>
    /// <param name="file">The CSV file containing tracking details to be uploaded. This file will be processed to extract data which will then be posted to the specified destination, ensuring accurate data conveyance and proper error handling.</param>

        Task UploadCsvFilePaymentReliabilityAsync(IFormFile file);

    /// <summary>
    /// Update the review date of a specific user's profile based on provided information.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile review date is being updated.</param>
    /// <param name="reviewDateUtc">The date and time (in UTC) for the review of the user's profile; defaults to null if not provided.</param>

        Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDate = null);

    /// <summary>
    /// Update the profile picture for a specified user.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose profile picture is being updated.</param>
    /// <param name="fileGuid">A Guid representing the unique identifier of the file that contains the new profile picture.</param>

        Task UpdateProfilePictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update the header picture for a specified user using the provided file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier of the user who is updating the header picture. It ensures the request is associated with the correct user.</param>
    /// <param name="fileGuid">The globally unique identifier of the file representing the new header picture. This ID ensures the correct file is being referenced for the update.</param>

        Task UpdateHeaderPictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update basic information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This is an integer value that specifies which user's information is being updated.</param>
    /// <param name="linkedInUrl">The LinkedIn URL of the user. This is an optional string that can be null, and it represents the user's LinkedIn profile link.</param>
    /// <param name="aboutMe">A brief description about the user. This is an optional string that can be null, providing additional information or a personal summary about the user.</param>

        Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe);

    /// <summary>
    /// Update the user's ranking appearance status based on the provided identifiers.
    /// </summary>
    /// <param name="userId">The unique identifier for the user, used to track user-specific data and ensure proper authorization.</param>
    /// <param name="schoolId">The unique identifier for the school, used to fetch and associate school-specific details.</param>
    /// <param name="doesAppearInRanking">A boolean flag indicating whether the user should appear in the ranking. This determines if the ranking data should be updated accordingly.</param>

        Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking);

    /// <summary>
    /// Update the status of a user's appearance in the learner directory, including their openness to collaboration, based on specified user and school identifiers.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom tracking details are being updated.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="doesAppearInLearnerDirectory">Indicates whether the user appears in the learner directory.</param>
    /// <param name="isOpenToCollaboration">Indicates whether the user is open to collaboration with other learners.</param>

        Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration);

    /// <summary>
    /// Update the actual location of a specified user by sending a command with the user's ID, country code, and timezone ID.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user for whom the location is being updated. This parameter is mandatory.</param>
    /// <param name="countryCode">An optional string indicating the ISO 3166-1 alpha-2 country code relevant to the user's location. This parameter is optional and may be null.</param>
    /// <param name="timezoneId">An optional string representing the IANA time zone identifier associated with the user's location. This parameter is optional and may be null.</param>

        Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId);

    /// <summary>
    /// Add a new professional experience record for a specified user.
    /// </summary>
    /// <param name="professionalExperienceIto">An input object containing professional experience details to be added. The object should encapsulate relevant information such as job titles, employment dates, and any other pertinent details about the user's professional background.</param>
    /// <param name="userId">The unique identifier for the user to whom the professional experience details belong. This integer is used to ensure that the correct user's information is updated.</param>
    /// <returns>Returns a task representing the asynchronous add operation.</returns>

        Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperience, int userId);

    /// <summary>
    /// Update the professional experience details for a specified user.
    /// </summary>
    /// <param name="professionalExperienceId">Unique identifier for the professional experience that needs to be updated.</param>
    /// <param name="professionalExperienceIto">Data transfer object containing the updated details of the professional experience.</param>
    /// <param name="userId">Unique identifier for the user whose professional experience is being updated.</param>

        Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId);

    /// <summary>
    /// Remove a specified professional experience for a user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience entry that needs to be removed.</param>
    /// <param name="userId">The unique identifier for the user whose professional experience entry needs to be removed.</param>

        Task RemoveUserProfessionalExperienceAsync(int id, int userId);

    /// <summary>
    /// Update the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">The identifier for the user. This is used to associate the provided study details with a specific user account.</param>
    /// <param name="studyInfos">The information about the study that needs to be posted. It contains all relevant details that will be used in tracking and data updates.</param>

        Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos);

    /// <summary>
    /// Update a user's notification registration information based on specified parameters, including user ID, school ID, notification type, and subscription statuses for email and push notifications.
    /// </summary>
    /// <param name="userId">The unique identifier of the user.</param>
    /// <param name="schoolId">The unique identifier of the school.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification to be updated.</param>
    /// <param name="isEmailSubscriptionActive">Indicates whether the email subscription is currently active. This can be null if the status is not applicable.</param>
    /// <param name="isPushSubscriptionActive">Indicates whether the push subscription is currently active. This can be null if the status is not applicable.</param>

        Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive);

    /// <summary>
    /// Update the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose first connection date is being updated. This integer is crucial as it determines which user's data will be tracked and updated.</param>
    /// <param name="connectionDateUtc">The optional date and time in UTC of the user's connection. If provided, this DateTime value will be used as the connection date; otherwise, the connection date will be set to a default value. This parameter is nullable.</param>

        Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDate = null);

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

        Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy);
    }
}
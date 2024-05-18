using Microsoft.AspNetCore.Http;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileWritingService
    {

    /// <summary>
    /// Update the reliability status of a user's payment based on their Salesforce ID.
    /// </summary>
    /// <param name="salesforceId">The Salesforce ID of the user whose payment reliability status is being updated.</param>
    /// <param name="code">A unique code associated with the payment reliability status update.</param>
    /// <param name="isCsvUpload">A boolean indicating whether the update is being uploaded via CSV.</param>
        Task UpdatePaymentReliabilityAsync(string salesforceId, string code, bool isCsvUpload);

    /// <summary>
    /// Upload a CSV file containing payment reliability data.
    /// </summary>
    /// <param name="file">The CSV file containing payment reliability data to be uploaded.</param>

        Task UploadCsvFilePaymentReliabilityAsync(IFormFile file);

    /// <summary>
    /// Update the review date of a user's profile.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile's review date is being updated.</param>
    /// <param name="reviewDateUtc">The UTC date and time when the review is to be updated. This parameter is optional and can be null.</param>

        Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDate = null);

    /// <summary>
    /// Update the profile picture for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile picture is being updated.</param>
    /// <param name="fileGuid">The globally unique identifier of the file representing the new profile picture.</param>

        Task UpdateProfilePictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update the header picture for a specified user using the provided file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose header picture is being updated.</param>
    /// <param name="fileGuid">The unique identifier for the file that will be used as the new header picture.</param>

        Task UpdateHeaderPictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update the basic information of a user based on their ID, LinkedIn URL, and description.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose basic information is to be updated.</param>
    /// <param name="linkedInUrl">The LinkedIn profile URL of the user. This parameter is optional and can be null.</param>
    /// <param name="aboutMe">A brief description or bio of the user. This parameter is optional and can be null.</param>

        Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe);

    /// <summary>
    /// Update the ranking status for a specified user in a specific school.
    /// </summary>
    /// <param name="userId">The ID of the user whose ranking status needs to be updated.</param>
    /// <param name="schoolId">The ID of the school where the user's ranking status will be updated.</param>
    /// <param name="doesAppearInRanking">Specifies whether the user should appear in the ranking (true) or not (false).</param>

        Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking);

    /// <summary>
    /// Update the appearance status of a user in the learner directory based on provided parameters such as user ID, school ID, appearance status, and collaboration openness.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose appearance status is to be updated in the learner directory.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="doesAppearInLearnerDirectory">A boolean flag indicating whether the user should appear in the learner directory.</param>
    /// <param name="isOpenToCollaboration">A boolean flag indicating whether the user is open to collaboration with others.</param>

        Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration);

    /// <summary>
    /// Update the current geographic location and timezone information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose geographic location and timezone information is being updated. This is a required parameter and should be an integer.</param>
    /// <param name="countryCode">The optional two-letter country code representing the user's current country. This parameter is a string and can be null if the country information is not available.</param>
    /// <param name="timezoneId">The optional identifier for the user's current timezone. This parameter is a string and may be null if the timezone information is not available.</param>

        Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId);

    /// <summary>
    /// Add a user's professional experience.
    /// </summary>
    /// <param name="professionalExperienceIto">An object containing the professional experience details to be added for the user.</param>
    /// <param name="userId">The unique identifier of the user for whom the professional experience is to be added.</param>
    /// <returns>Returns a task representing the asynchronous operation.</returns>

        Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperience, int userId);

    /// <summary>
    /// Update the professional experience information for a specified user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience to be updated.</param>
    /// <param name="professionalExperienceIto">The object containing updated information about the professional experience.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being updated.</param>

        Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId);

    /// <summary>
    /// Remove a user’s professional experience based on the provided experience ID and user ID.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience to be removed.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is to be removed.</param>

        Task RemoveUserProfessionalExperienceAsync(int id, int userId);

    /// <summary>
    /// Update the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose study information is to be updated.</param>
    /// <param name="studyInfos">A StudyIto object that contains the latest study information to be updated for the specified user.</param>

        Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos);

    /// <summary>
    /// Update the notification preferences for a specified user based on provided parameters such as school ID, notification type code, and subscription statuses for email and push notifications.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose notification preferences are being updated.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user's notification preferences.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification (e.g., email, SMS, push notification) that the user is subscribed to.</param>
    /// <param name="isEmailSubscriptionActive">A boolean value indicating whether the user's email subscription is active. This can be null if there is no change to the email subscription status.</param>
    /// <param name="isPushSubscriptionActive">A boolean value indicating whether the user's push notification subscription is active. This can be null if there is no change to the push subscription status.</param>

        Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive);

    /// <summary>
    /// Update the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the first connection date is to be updated. It is an integer and cannot be null.</param>
    /// <param name="connectionDateUtc">The first connection date and time for the user, in UTC. This is optional and can be null. If not provided, the current date and time will be used.</param>

        Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDate = null);

    /// <summary>
    /// Create a user profile by obtaining the civility information, generating a pseudo name if none is provided, and then sending the user profile creation command with the provided details and default values for the avatar URL and header profile background URL.
    /// </summary>
    /// <param name="civilityId">The unique identifier representing the user's civility status. It is an integer value that determines the salutation, such as Mr., Ms., etc.</param>
    /// <param name="lastName">The last name of the user. This is a required string field that stores the user's family name.</param>
    /// <param name="firstName">The first name of the user. This is a required string field that stores the user's given name.</param>
    /// <param name="birthDate">The birth date of the user. This field stores the user's date of birth and is of type DateOnly, which represents a date without time.</param>
    /// <param name="email">The user's email address. This is a required string field used for user identification and communication.</param>
    /// <param name="pseudo">An optional pseudonym for the user. This string field allows the user to have a nickname or handle, distinct from their first and last name.</param>
    /// <param name="isOfficial">A boolean flag indicating whether the user profile is marked as an official profile. This helps differentiate official entities from regular users.</param>
    /// <param name="isTester">A boolean flag that signifies whether the user is a tester. This can be used to grant specific permissions or access for testing environments.</param>
    /// <param name="maidenName">An optional field for the user's maiden name if applicable. This string allows storage of the user's last name prior to marriage.</param>
    /// <param name="createBy">The identifier of the entity that created the user profile. This string stores information about who or what process initiated the profile creation.</param>
    /// <returns>Returns a Task containing the created UserProfile object.</returns>

        Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy);
    }
}
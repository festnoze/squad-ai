using Microsoft.AspNetCore.Http;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileWritingService
    {

    /// <summary>
    /// Update the reliability status of a payment using a specific Salesforce ID as a reference. Ensure the provided Salesforce ID is valid, retrieve the associated user ID, and proceed if a valid user ID is found.
    /// </summary>
    /// <param name="salesforceId">The Salesforce ID used to identify and update the reliability status of a payment. Ensure the provided Salesforce ID is valid.</param>
    /// <param name="code">A unique code associated with the payment process. This code is necessary for identifying the specific action to be taken on the payment.</param>
    /// <param name="isCsvUpload">A boolean flag indicating whether the payment update is being performed via a CSV upload. Set to true if the update is from a CSV file, otherwise false.</param>
        Task UpdatePaymentReliabilityAsync(string salesforceId, string code, bool isCsvUpload);

    /// <summary>
    /// Attempt to upload a payment reliability data in CSV format.
    /// </summary>
    /// <param name="file">The CSV file containing payment reliability data to be uploaded.</param>

        Task UploadCsvFilePaymentReliabilityAsync(IFormFile file);

    /// <summary>
    /// Update the review date of a user's profile based on the provided user ID and review date.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile review date needs to be updated.</param>
    /// <param name="reviewDateUtc">The updated review date of the user's profile in UTC. If null, the current date and time will be used.</param>

        Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDate = null);

    /// <summary>
    /// Update a user's profile picture using a given file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile picture is to be updated.</param>
    /// <param name="fileGuid">The unique file identifier for the new profile picture to be set.</param>

        Task UpdateProfilePictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update the header picture for a specified user with the provided file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose header picture is to be updated.</param>
    /// <param name="fileGuid">The unique identifier of the file that contains the new header picture.</param>

        Task UpdateHeaderPictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update basic information for a user with provided LinkedIn URL and description.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose basic information needs to be updated.</param>
    /// <param name="linkedInUrl">The LinkedIn profile URL of the user. This parameter is optional and can be null.</param>
    /// <param name="aboutMe">A brief description or biography about the user. This parameter is optional and can be null.</param>

        Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe);

    /// <summary>
    /// Update the ranking status for a specified user in a particular school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose ranking status is to be updated.</param>
    /// <param name="schoolId">The unique identifier for the school in which the user's ranking status is to be updated.</param>
    /// <param name="doesAppearInRanking">A boolean flag indicating whether the user should appear in the ranking (true) or not (false).</param>

        Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking);

    /// <summary>
    /// Update the learner directory status for a specified user to reflect visibility and collaboration settings.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose learner directory status is being updated.</param>
    /// <param name="schoolId">The unique identifier of the school to which the user belongs.</param>
    /// <param name="doesAppearInLearnerDirectory">A boolean indicating whether the user should appear in the learner directory.</param>
    /// <param name="isOpenToCollaboration">A boolean indicating whether the user is open to collaboration with other learners.</param>

        Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration);

    /// <summary>
    /// Update the current location details for a specified user, including country and timezone information.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose location details are being updated.</param>
    /// <param name="countryCode">The code representing the country for the user's current location. It can be null if the country is not specified.</param>
    /// <param name="timezoneId">The identifier for the timezone of the user's current location. It can be null if the timezone is not specified.</param>

        Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId);

    /// <summary>
    /// Add a new professional experience for a specified user.
    /// </summary>
    /// <param name="professionalExperienceIto">An instance containing the professional experience information to be added for the specified user.</param>
    /// <param name="userId">The unique identifier of the user for whom the professional experience is being added.</param>
    /// <returns>Returns a Task representing the asynchronous operation.</returns>

        Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperience, int userId);

    /// <summary>
    /// Update a user's professional experience based on provided details.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience entry to be updated.</param>
    /// <param name="professionalExperienceIto">An object containing the new details of the professional experience to update.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being updated.</param>

        Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId);

    /// <summary>
    /// Remove a specified professional experience for a user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience to be removed.</param>
    /// <param name="userId">The unique identifier of the user from whom the professional experience will be removed.</param>

        Task RemoveUserProfessionalExperienceAsync(int id, int userId);

    /// <summary>
    /// Replace the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose study information is to be replaced.</param>
    /// <param name="studyInfos">The new study information that will replace the existing information for the specified user.</param>

        Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos);

    /// <summary>
    /// Update notification registration for a specified user based on provided parameters.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the notification registration is to be updated.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification to be updated (e.g., email, push).</param>
    /// <param name="isEmailSubscriptionActive">A nullable boolean indicating whether the email subscription is active. If null, no changes will be made.</param>
    /// <param name="isPushSubscriptionActive">A nullable boolean indicating whether the push subscription is active. If null, no changes will be made.</param>

        Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive);

    /// <summary>
    /// Update the first connection date for a specified user using the UTC date provided.
    /// </summary>
    /// <param name="userId">An integer representing the ID of the user whose first connection date is to be updated.</param>
    /// <param name="connectionDateUtc">An optional DateTime representing the UTC date of the user's first connection. If not provided, the current date and time may be used.</param>

        Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDate = null);

    /// <summary>
    /// Create a user profile by fetching necessary details including civility, pseudo, and other personal information, and then sending a command to create the profile with default avatar and background URLs.
    /// </summary>
    /// <param name="civilityId">An integer representing the user's civility identifier.</param>
    /// <param name="lastName">A string representing the user's last name.</param>
    /// <param name="firstName">A string representing the user's first name.</param>
    /// <param name="birthDate">A DateOnly object representing the user's date of birth.</param>
    /// <param name="email">A string representing the user's email address.</param>
    /// <param name="pseudo">An optional string representing the user's pseudonym or nickname.</param>
    /// <param name="isOfficial">A boolean indicating if the user is an official.</param>
    /// <param name="isTester">A boolean indicating if the user is a tester.</param>
    /// <param name="maidenName">An optional string representing the user's maiden name.</param>
    /// <param name="createBy">A string identifying who created the user profile.</param>
    /// <returns>Returns a Task representing the asynchronous creation of a user profile.</returns>

        Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy);
    }
}
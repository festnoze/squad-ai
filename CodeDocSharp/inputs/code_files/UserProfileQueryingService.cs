namespace Studi.Api.Lms.Application.Services;

using MediatR;
using Studi.Api.Core.Exceptions.ErrorCodesLocalization.Base;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Lms.User.Application.Interfaces;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;
using Studi.Api.Lms.User.Domain.Aggregates.User.Queries;
using Studi.Api.Lms.User.Localization.Error.GeneratedClasses;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Application.Services.CustomWebResource;
using Studi.Api.Core.Pagination.Filter;
using Studi.Api.Lms.User.Application.Decorators;
using Studi.Api.Lms.User.Application.Tools;
using Studi.Api.Lms.User.Application.Mapper;
using Studi.Api.Core.Pagination.Sort;
using Studi.Api.Lms.User.Application.ATOs;
using Studi.Api.Lms.User.Application.Services.Civility;
using Studi.Api.Lms.User.Common.RepositoriesInterfaces;

[ScopedService(typeof(IUserProfileQueryingService))]
public class UserProfileQueryingService : IUserProfileQueryingService
{
    private readonly IMediator _mediator;
    private readonly ICustomWebResourceService _customWebResource;
    private readonly ICivilityService _civilityService;
    private readonly IUserRepository _userRepository;


    /// <summary>
    /// Initialize required dependencies for handling user profile queries. Ensure provided mediator, custom web resource, and civility service are not null, otherwise, throw exceptions. Assign the user repository.
    /// </summary>
    /// <param name="mediator">An instance of IMediator used for sending various kinds of messages that handle business logic.</param>
    /// <param name="customWebResource">Service responsible for handling custom web resources required by the application.</param>
    /// <param name="civilityService">Service used to retrieve and manage civility information for users.</param>
    /// <param name="userRepository">Repository interface for accessing user data from the data store.</param>
    public UserProfileQueryingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserRepository userRepository)
    {
        _mediator = mediator ?? throw new ArgumentNullException();
        _customWebResource = customWebResource ?? throw new ArgumentNullException();
        _civilityService = civilityService ?? throw new ArgumentNullException();
        _userRepository = userRepository;
    }


    /// <summary>
    /// Verify the reliability of a user's payment status by checking for a non-negative, non-zero user ID and querying the user repository.
    /// </summary>
    /// <param name="userId">The unique identifier representing the user whose profile and civility information are being retrieved.</param>
    /// <returns>Returns a task with the user's payment reliability status.</returns>
    public async Task<string?> GetPaymentReliabilityAsync(int userId)
    {
        Guard.Against.NegativeOrZero(userId, ErrorCode.Api.Lms.User.DataValidation.Common.UserId.NegativeOrZero);
        return await _userRepository.GetPaymentReliabilityAsync(userId);
    }



    /// <summary>
    /// Retrieve the basic information of a specified user while checking for null and handling exceptions if the user does not exist.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile is to be retrieved.</param>
    /// <param name="schoolId">The ID of the school to associate with the user’s profile.</param>
    /// <param name="loadSchoolOptions">A flag indicating whether to load additional school options. Default is false.</param>
    /// <returns>Returns basic user information asynchronously.</returns>
    public async Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false)
    {
        var user = await _mediator.Send(new UserBaseQuery(userId));
        Guard.Against.Null(user, ErrorCode.Api.Lms.User.DataValidation.Query.User.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        var userBasicInfoIto = await _mediator.Send(new UserBasicInfoQuery(userId));
        user!.SetBasicInfoInformations(BasicInfoModel.CreateExisting(userBasicInfoIto!));

        if (loadSchoolOptions)
        {
            var userSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
            Guard.Against.Null(userSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

            user!.SetUserSchoolOptions(UserSchoolOptionsModel.CreateExisting(userSchoolOptions!));
        }

        return user!;
    }


    /// <summary>
    /// Retrieve public information for a specified user and their school options.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile needs to be retrieved.</param>
    /// <param name="schoolId">The identifier of the school to which the user belongs. It's used to retrieve relevant public information.</param>
    /// <returns>Returns a user’s public information and school options asynchronously.</returns>
    public async Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId)
    {
        var user = await _mediator.Send(new UserPublicInfoQuery(userId));
        Guard.Against.Null(user, ErrorCode.Api.Lms.User.DataValidation.Query.PublicInfo.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString()); //TODO Localize

        var userSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        if (userSchoolOptions != null)
        {
            user!.SetUserSchoolOptions(UserSchoolOptionsModel.CreateExisting(userSchoolOptions!));

            var userScoresItos = await _mediator.Send(new UserScoresQuery(userId, schoolId));
            user!.SetUserScoresModel(userScoresItos is null ? null : UserScoresModel.CreateExisting(userScoresItos!));

            var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
            Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);
            user!.SetTrainings(TrainingModel.CreateExistingList(userTrainingsItos!));
        }

        return user!;
    }


    /// <summary>
    /// Retrieve user information along with their course registrations for a specified user within a given school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information are being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to which the user is associated. This helps in contextually retrieving the user's profile information specific to the school.</param>
    /// <returns>Returns user's profile and course registrations asynchronously.</returns>
    //[Obsolete("replaced by Trainings")]
    //public async Task<UserModel> GetUserWithCoursesRegistrationsAsync(int userId, int schoolId)
    //{
    //    var user = await _mediator.Send(new UserCoursesRegistrationsQuery(userId, schoolId));
    //    return user.UserCoursesRegistrations.First().ToIto();
    //}


    /// <summary>
    /// Retrieve personal information for a specified user while ensuring the data is not null.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile and civility information are being retrieved. This should be an integer value.</param>
    /// <returns>Returns a user object containing personal and civility information.</returns>
    public async Task<UserModel> GetUserWithPersonalInfosAsync(int userId)
    {
        var userWPersonalInfos = await _mediator.Send(new UserPersonnalInformationsQuery(userId));
        Guard.Against.Null(userWPersonalInfos, ErrorCode.Api.Lms.User.DataValidation.Query.PersonnalInfos.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        return userWPersonalInfos!;
    }


    /// <summary>
    /// Retrieve school options available for a specified user, ensuring the data exists and is valid before returning it as an existing user school options model.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user.</param>
    /// <returns>Returns user-specific school options model.</returns>
    public async Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId)
    {
        var userWSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        Guard.Against.Null(userWSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

        return UserSchoolOptionsModel.CreateExisting(userWSchoolOptions!);
    }


    /// <summary>
    /// Retrieve the professional experiences for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose professional experiences are being retrieved.</param>
    /// <returns>Returns a list of the user's professional experiences.</returns>
    public async Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId)
    {
        return (await _mediator.Send(new UserProfessionalExperiencesQuery(userId))).ProfessionalExperiences;
    }


    /// <summary>
    /// Retrieve the review date of a user's profile based on the specified user ID.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information is being retrieved. This is an integer value.</param>
    /// <returns>Returns the profile review date as a Task<DateTime> instance.</returns>
    public async Task<DateTime?> GetUserProfileReviewDateAsync(int userId)
    {
        return await _mediator.Send(new UserProfileReviewDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the last study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civil information is being retrieved.</param>
    /// <returns>Returns the latest study details for the specified user.</returns>
    public async Task<StudyModel?> GetUserLastStudyInfosAsync(int userId)
    {
        return await _mediator.Send(new UserLastStudyInfosQuery(userId));
    }


    /// <summary>
    /// Retrieve a list of contract types relevant to professional experiences.
    /// </summary>
    /// <returns>Returns a list of contract types.</returns>
    public async Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync()
    {
        return await _mediator.Send(new AllContractTypesForProfessionalExperiencesQuery());
    }


    /// <summary>
    /// Retrieve the trainings for a specified user within a particular school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information are being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school which will be used to fetch the user's profile and civility information.</param>
    /// <returns>Returns a list of the user's training sessions within the specified school.</returns>
    public async Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId)
    {
        var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
        Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);

        return TrainingModel.CreateExistingList(userTrainingsItos);
    }


    /// <summary>
    /// Retrieve notification settings for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to filter the user's notifications.</param>
    /// <returns>Returns the user's notification settings filtered by school.</returns>
    public async Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserNotificationsSettingsQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the time zone for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile and civility information is being retrieved.</param>
    /// <returns>Returns the user's time zone identifier.</returns>
    public async Task<string> GetUserTimeZoneAsync(int userId)
    {
        return await _mediator.Send(new UserTimeZoneQuery(userId));
    }


    /// <summary>
    /// Retrieve user configuration information based on specified user and school identifiers.
    /// </summary>
    /// <param name="userId">Represents the unique identifier for the user whose profile information is being retrieved. This parameter is critical to identify and fetch the correct user data.</param>
    /// <param name="schoolId">Denotes the unique identifier of the school associated with the user. This parameter is used to filter and fetch user information specific to a particular school entity.</param>
    /// <returns>Returns user configuration information as an asynchronous task.</returns>
    public async Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserConfigInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the last session information for a specified user within a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user's profile.</param>
    /// <returns>Returns the last session details for a given user in a specific school.</returns>
    public async Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserLastSessionInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Get the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information is to be retrieved.</param>
    /// <returns>Returns the first connection date of the specified user.</returns>
    public async Task<DateTime?> GetUserFirstConnectionDateAsync(int userId)
    {
        return await _mediator.Send(new UserFirstConnectionDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the avatar URL for a specified user, returning a default URL if none is found.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile and civility information are being retrieved.</param>
    /// <returns>Returns the user's avatar URL or a default URL if unavailable.</returns>
    public async Task<string> GetAvatarUrlAsync(int userId)
    {
        var url = await _mediator.Send(new UserAvatarUrlQuery(userId));

        if (!string.IsNullOrEmpty(url) 
            && !string.IsNullOrWhiteSpace(url))
            return url;

        return _customWebResource.DefaultAvatarUrl;
    }


    /// <summary>
    /// Check if a user exists by a specified email.
    /// </summary>
    /// <param name="email">The email address used to identify and retrieve the user's profile and civility information.</param>
    /// <returns>Returns true if the user exists; otherwise, false.</returns>
    public async Task<bool> ExistUserByEmailAsync(string email)
    {
        return await _mediator.Send(new UserExistByEmailQuery(email));
    }


    /// <summary>
    /// Check for the existence of a user based on a provided pseudonym.
    /// </summary>
    /// <param name="pseudo">The pseudo or nickname of the user whose profile is being retrieved. This parameter is critical in identifying the specific user in the system.</param>
    /// <returns>Returns a Task<bool> indicating if the user exists by the given pseudonym.</returns>
    public async Task<bool> ExistUserByPseudoAsync(string pseudo)
    {
        return await _mediator.Send(new UserExistByPseudoQuery(pseudo));
    }


    /// <summary>
    /// Generate a pseudonym for a user based on their first name and last name.
    /// </summary>
    /// <param name="firstName">The first name of the user whose profile is being retrieved.</param>
    /// <param name="lastName">The last name of the user whose profile is being retrieved.</param>
    /// <returns>Returns a pseudonym generated from the user's first and last name.</returns>
    public async Task<string> GeneratePseudoAsync(string firstName, string lastName)
    {
        return await _mediator.Send(new UserGeneratePseudoQuery(firstName, lastName));
    }


    /// <summary>
    /// Count the total number of user profiles based on specified filtering criteria.
    /// </summary>
    /// <param name="filtersCompositions">Optional. A collection of filters composed using the IFiltersComposition interface for filtering the profiles. This parameter can be null.</param>
    /// <returns>Returns the total count of user profiles matching the specified filters.</returns>
    public async Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);

        return await _mediator.Send(new UserProfilesCountQuery(filtersCompositions));
    }


    /// <summary>
    /// Retrieve user profiles based on specified filters and sorting, then map the results with corresponding civilities.
    /// </summary>
    /// <param name="skip">The number of items to skip before starting to collect the result set. Useful for pagination.</param>
    /// <param name="take">The number of items to take for the result set. Defines the size of the result.</param>
    /// <param name="filtersCompositions">A collection of filters to apply to the result set, allowing for complex querying. Can be null.</param>
    /// <param name="sort">Defines the sorting criteria for the result set. Can be null.</param>
    /// <returns>Returns a list of user profiles with applied filters and sorting.</returns>
    public async Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);
        PaginationTools.TransformSortFieldName(sort, fieldNameDecorator);

        var data = await _mediator.Send(new UserProfilesQuery(skip, take, filtersCompositions, sort));

        if(!data.Any())
            return Enumerable.Empty<IUserProfileRAto>();

        var civilities = this._civilityService.GetCivilities();
        return data.Select(q => ItoToAtoMapper.ToUserProfileRAto(q, civilities.FirstOrDefault(c => c.Name == q.Civility)?.Id));
    }


    /// <summary>
    /// Retrieve a user's profile along with their civility information, if available.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile is being retrieved.</param>
    /// <returns>Returns a user's profile and civility information.</returns>
    public async Task<IUserProfileRAto> GetUserProfileAsync(int userId)
    {
        var data = await _mediator.Send(new UserProfileQuery(userId));
        var civility = !string.IsNullOrEmpty(data.Civility) ? this._civilityService.GetCivilityByName(data.Civility!) : null;

        return ItoToAtoMapper.ToUserProfileRAto(data, civility?.Id);
    }
}
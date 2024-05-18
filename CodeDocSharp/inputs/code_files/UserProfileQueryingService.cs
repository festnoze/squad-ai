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
    /// Initialize the class by assigning and validating essential services and resources.
    /// </summary>
    /// <param name="mediator">The mediator instance used to coordinate requests and responses between different components.</param>
    /// <param name="customWebResource">A service to handle custom web resources necessary for the application.</param>
    /// <param name="civilityService">A service that provides operations related to user civility data.</param>
    /// <param name="userRepository">A repository that manages user data and interactions with the data source.</param>
    public UserProfileQueryingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserRepository userRepository)
    {
        _mediator = mediator ?? throw new ArgumentNullException();
        _customWebResource = customWebResource ?? throw new ArgumentNullException();
        _civilityService = civilityService ?? throw new ArgumentNullException();
        _userRepository = userRepository;
    }


    /// <summary>
    /// Check the validity of a specified user's ID and retrieve their payment reliability status.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose payment reliability status is to be checked.</param>
    /// <returns>Returns a user's payment reliability status.</returns>
    public async Task<string?> GetPaymentReliabilityAsync(int userId)
    {
        Guard.Against.NegativeOrZero(userId, ErrorCode.Api.Lms.User.DataValidation.Common.UserId.NegativeOrZero);
        return await _userRepository.GetPaymentReliabilityAsync(userId);
    }



    /// <summary>
    /// Retrieve basic information for a specified user and verify the existence of user data before associating additional information.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose basic information is being retrieved.</param>
    /// <param name="schoolId">The identifier for the school to which the user is associated.</param>
    /// <param name="loadSchoolOptions">A boolean flag indicating whether additional options associated with the school should be loaded. Default is false.</param>
    /// <returns>Returns basic user information with verification and optional school data.</returns>
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
    /// Retrieve the public information of a user, ensuring the user exists, then verify if there are school options for the user in a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user. This parameter is used to retrieve and verify the public information of the user ensuring they exist.</param>
    /// <param name="schoolId">The unique identifier of the school. This parameter is used to check if there are school options available for the user in the specified school.</param>
    /// <returns>Returns the user's public info and school options asynchronously.</returns>
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
    /// Retrieve a user's course registration details for a specified user and school, then return the first course registration.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose course registration details need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to filter the user's course registrations.</param>
    /// <returns>Returns the first course registration for the specified user and school.</returns>
    //[Obsolete("replaced by Trainings")]
    //public async Task<UserModel> GetUserWithCoursesRegistrationsAsync(int userId, int schoolId)
    //{
    //    var user = await _mediator.Send(new UserCoursesRegistrationsQuery(userId, schoolId));
    //    return user.UserCoursesRegistrations.First().ToIto();
    //}


    /// <summary>
    /// Retrieve detailed personal information for a specified user and ensure the data is not null, returning the verified personal information.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose personal information is to be retrieved. It ensures that the correct user's data is fetched.</param>
    /// <returns>Returns verified personal details of a specified user.</returns>
    public async Task<UserModel> GetUserWithPersonalInfosAsync(int userId)
    {
        var userWPersonalInfos = await _mediator.Send(new UserPersonnalInformationsQuery(userId));
        Guard.Against.Null(userWPersonalInfos, ErrorCode.Api.Lms.User.DataValidation.Query.PersonnalInfos.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        return userWPersonalInfos!;
    }


    /// <summary>
    /// Retrieve school options for a specific user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This parameter is used to specify the user for whom the school options need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school. This parameter is used to specify the school options related to the provided school ID.</param>
    /// <returns>Returns available school options for the specified user and school.</returns>
    public async Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId)
    {
        var userWSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        Guard.Against.Null(userWSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

        return UserSchoolOptionsModel.CreateExisting(userWSchoolOptions!);
    }


    /// <summary>
    /// Retrieve professional experiences for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user whose professional experiences are to be retrieved. This should be an integer.</param>
    /// <returns>Returns a list of user's professional experiences.</returns>
    public async Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId)
    {
        return (await _mediator.Send(new UserProfessionalExperiencesQuery(userId))).ProfessionalExperiences;
    }


    /// <summary>
    /// Retrieve the review date of the user profile for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile review date is to be retrieved.</param>
    /// <returns>Returns the review date of the user's profile.</returns>
    public async Task<DateTime?> GetUserProfileReviewDateAsync(int userId)
    {
        return await _mediator.Send(new UserProfileReviewDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the most recent study information for a specific user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose most recent study information is being retrieved.</param>
    /// <returns>Returns the latest study information of the specified user.</returns>
    public async Task<StudyModel?> GetUserLastStudyInfosAsync(int userId)
    {
        return await _mediator.Send(new UserLastStudyInfosQuery(userId));
    }


    /// <summary>
    /// Retrieve a list of contract types applicable to professional experiences.
    /// </summary>
    /// <returns>Returns a list of contract types for professional experiences.</returns>
    public async Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync()
    {
        return await _mediator.Send(new AllContractTypesForProfessionalExperiencesQuery());
    }


    /// <summary>
    /// Retrieve a list of existing training models for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose training models are being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to which the user belongs.</param>
    /// <returns>Returns a list of the user's training models.</returns>
    public async Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId)
    {
        var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
        Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);

        return TrainingModel.CreateExistingList(userTrainingsItos);
    }


    /// <summary>
    /// Retrieve the notification settings for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose notification settings are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to which the user belongs.</param>
    /// <returns>Returns a list of user's notification settings for the specified school.</returns>
    public async Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserNotificationsSettingsQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the time zone information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose time zone information needs to be retrieved.</param>
    /// <returns>Returns the user's time zone information asynchronously.</returns>
    public async Task<string> GetUserTimeZoneAsync(int userId)
    {
        return await _mediator.Send(new UserTimeZoneQuery(userId));
    }


    /// <summary>
    /// Retrieve configuration information for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose configuration information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user.</param>
    /// <returns>Returns a task with user's school-specific configuration details.</returns>
    public async Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserConfigInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the latest session information for a specific user in a designated school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user for whom the latest session information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school where the session information is being fetched.</param>
    /// <returns>Returns the latest session details for the specified user in a given school.</returns>
    public async Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserLastSessionInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose first connection date is to be retrieved.</param>
    /// <returns>Returns the user's first connection date as an asynchronous task.</returns>
    public async Task<DateTime?> GetUserFirstConnectionDateAsync(int userId)
    {
        return await _mediator.Send(new UserFirstConnectionDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the avatar URL for a specified user, returning a default URL if no specific URL is found or if the found URL is invalid.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the avatar URL is to be retrieved.</param>
    /// <returns>Returns the avatar URL for the specified user.</returns>
    public async Task<string> GetAvatarUrlAsync(int userId)
    {
        var url = await _mediator.Send(new UserAvatarUrlQuery(userId));

        if (!string.IsNullOrEmpty(url) 
            && !string.IsNullOrWhiteSpace(url))
            return url;

        return _customWebResource.DefaultAvatarUrl;
    }


    /// <summary>
    /// Check if a user exists by a specified email address.
    /// </summary>
    /// <param name="email">The email address of the user to check. This parameter is required to identify which user's existence needs to be verified.</param>
    /// <returns>Returns a boolean indicating if the user exists by the given email address.</returns>
    public async Task<bool> ExistUserByEmailAsync(string email)
    {
        return await _mediator.Send(new UserExistByEmailQuery(email));
    }


    /// <summary>
    /// Check the existence of a user by their pseudo.
    /// </summary>
    /// <param name="pseudo">The pseudo of the user whose existence is being checked in the method ExistUserByPseudoAsync.</param>
    /// <returns>Returns a boolean indicating if a user exists by their pseudo.</returns>
    public async Task<bool> ExistUserByPseudoAsync(string pseudo)
    {
        return await _mediator.Send(new UserExistByPseudoQuery(pseudo));
    }


    /// <summary>
    /// Generate a pseudo name by sending a query with the specified first and last names.
    /// </summary>
    /// <param name="firstName">The first name to be used in generating a pseudo name.</param>
    /// <param name="lastName">The last name to be used in generating a pseudo name.</param>
    /// <returns>Returns the generated pseudo name based on the given first and last names.</returns>
    public async Task<string> GeneratePseudoAsync(string firstName, string lastName)
    {
        return await _mediator.Send(new UserGeneratePseudoQuery(firstName, lastName));
    }


    /// <summary>
    /// Count the number of user profiles, applying specified filtering conditions.
    /// </summary>
    /// <param name="filtersCompositions">Optional. A collection of filter compositions to apply when counting user profiles. If no filters are provided, the count will cover all profiles.</param>
    /// <returns>Returns the total count of user profiles matching the specified filters.</returns>
    public async Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);

        return await _mediator.Send(new UserProfilesCountQuery(filtersCompositions));
    }


    /// <summary>
    /// Retrieve user profiles based on pagination and filtering criteria, and map associated civility information.
    /// </summary>
    /// <param name="skip">The number of records to skip in the pagination. Used for retrieving the next set of records.</param>
    /// <param name="take">The number of records to take in the pagination. This controls the size of the data set retrieved.</param>
    /// <param name="filtersCompositions">A collection of filters to apply to the data retrieval. These filters help in narrowing down the data based on certain criteria.</param>
    /// <param name="sort">The sorting criteria for ordering the user profiles. It allows the data to be sorted based on specific fields.</param>
    /// <returns>Returns a list of user profiles with associated civility information.</returns>
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
    /// Retrieve the user profile along with the associated civility information if available.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile is to be retrieved.</param>
    /// <returns>Returns the user profile with optional civility details.</returns>
    public async Task<IUserProfileRAto> GetUserProfileAsync(int userId)
    {
        var data = await _mediator.Send(new UserProfileQuery(userId));
        var civility = !string.IsNullOrEmpty(data.Civility) ? this._civilityService.GetCivilityByName(data.Civility!) : null;

        return ItoToAtoMapper.ToUserProfileRAto(data, civility?.Id);
    }
}
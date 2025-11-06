SELECT
    thr.user_id,
    ctx.context_filter,
    rol.name,
    msg.content
FROM public.messages msg
JOIN public.roles rol ON rol.id = msg.role_id
JOIN public.threads thr ON thr.id = msg.thread_id
JOIN public.users usr ON usr.id = thr.user_id
JOIN public.contexts ctx ON ctx.id = thr.context_id
WHERE usr.lms_user_id = '199520'
ORDER BY thr.user_id, thr.context_id, msg.created_at ASC

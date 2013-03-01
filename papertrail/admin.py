from papertrail import log


class AdminEventLoggerMixin(object):
    '''
    Mixin for ModelAdmin classes to log admin actions to the papertrail
    application as well as to Django's built-in admin logging.
    '''

    def log_addition(self, request, object):
        super(AdminEventLoggerMixin, self).log_addition(request, object)
        return log('Created object',
                   type='admin-edit',
                   acting_user=request.user,
                   instance=object)

    def log_change(self, request, object, message):
        super(AdminEventLoggerMixin, self).log_change(request, object, message)
        return log('Updated object',
                   type='admin-edit',
                   data={'message': message},
                   acting_user=request.user,
                   instance=object)

    def log_deletion(self, request, object, object_repr):
        super(AdminEventLoggerMixin, self).log_deletion(request, object, object_repr)
        return log('Deleted object',
                   type='admin-edit',
                   acting_user=request.user,
                   instance=object)

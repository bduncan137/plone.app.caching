from zope.interface import implements, Interface
from zope.component import adapts, queryUtility, queryMultiAdapter
from zope.pagetemplate.interfaces import IPageTemplate

from plone.registry.interfaces import IRegistry

from plone.caching.interfaces import ICacheInterceptor, IResponseMutator
from plone.caching.interfaces import IOperationLookup
from plone.caching.interfaces import ICacheSettings

from plone.app.caching.interfaces import IPloneCacheSettings

from Acquisition import aq_base
from Products.CMFDynamicViewFTI.interfaces import IBrowserDefault

class PageTemplateLookup(object):
    """Page templates defined through skin layers or created through the web
    are published as one of the following types of object:
    
    ``Products.CMFCore.FSPageTemplate.FSPageTemplate``
        Templates in a filesystem directory view
    ``Products.PageTemplates.ZopePageTemplate.ZopePageTemplate``
        A template created or customised through the web
    ``Products.CMFFormController.FSControllerPageTemplate.FSControllerPageTemplate``
        A CMFFormController page template in a filesystem directory view
    ``Products.CMFFormController.ControllerPageTemplate.ControllerPageTemplate``
        A CMFFormController page template created or customised through the
        web.
    
    All of these implement ``IPageTemplate``, but there is typically not a
    meaningful per-resource interface or class. Therefore, we implement
    different lookup semantics for these objects when published:
    
    * First, look up the page template name in the registry under the key
      ``plone.app.caching.interfaces.IPloneCacheSettings.templateRulesetMapping``.
      If this is found, look up the corresponding interceptor or mutator as
      normal.
    * If no template-specific mapping is found, find the ``__parent__`` of the
      template. If this is a content type, check whether the template is one
      of its default views. If so, look up a cache ruleset under the key
      ``plone.app.caching.interfaces.IPloneCacheSettings.contentTypeRulesetMapping``. 
      If found, look up the corresponding interceptor or mutator as normal.
    * Otherwise, abort.
    
    Note that this lookup is *not* invoked for a view which happens to use a
    page template to render itself.
    """
    
    implements(IOperationLookup)
    adapts(IPageTemplate, Interface)
    
    def __init__(self, published, request):
        self.published = published
        self.request = request
    
    def getResponseMutator(self):
        nyet = (None, None, None,)
    
        registry = queryUtility(IRegistry)
        if registry is None:
            return nyet
    
        cacheSettings = registry.forInterface(ICacheSettings, check=False)
        if not cacheSettings.enabled:
            return nyet
        
        ploneCacheSettings = registry.forInterface(IPloneCacheSettings, check=False)
        
        rule = self._getRuleset(cacheSettings, ploneCacheSettings)
        if rule is None:
            return nyet
        
        if cacheSettings.mutatorMapping is None:
            return nyet
    
        name = cacheSettings.mutatorMapping.get(rule, None)
        if name is None:
            return nyet
    
        mutator = queryMultiAdapter((self.published, self.request), IResponseMutator, name=name)
        return rule, name, mutator
    
    def getCacheInterceptor(self):
        nyet = (None, None, None,)
    
        registry = queryUtility(IRegistry)
        if registry is None:
            return nyet
    
        cacheSettings = registry.forInterface(ICacheSettings, check=False)
        if not cacheSettings.enabled:
            return nyet
        
        ploneCacheSettings = registry.forInterface(IPloneCacheSettings, check=False)
        
        rule = self._getRuleset(cacheSettings, ploneCacheSettings)
        if rule is None:
            return nyet
        
        if cacheSettings.interceptorMapping is None:
            return nyet
    
        name = cacheSettings.interceptorMapping.get(rule, None)
        if name is None:
            return nyet
    
        interceptor = queryMultiAdapter((self.published, self.request), ICacheInterceptor, name=name)
        return rule, name, interceptor
    
    def _getRuleset(self, cacheSettings, ploneCacheSettings):
        """Helper method to look up a ruleset for the published template.
        """
        
        # First, try to look up the template name in the appropriate mapping
        templateName = getattr(self.published, '__name__', None)
        if templateName is None:
            return None
        
        if ploneCacheSettings.templateRulesetMapping is not None:
            name = ploneCacheSettings.templateRulesetMapping.get(templateName, None)
            if name is not None:
                return name
        
        # Next, check if this is the default view of the context, and if so
        # try to look up the name of the context in the appropriate mapping
        if ploneCacheSettings.contentTypeRulesetMapping is None:
            return None
        
        parent = getattr(self.published, '__parent__', None)
        if parent is None:
            return None
        
        parentPortalType = getattr(aq_base(parent), 'portal_type', None)
        if parentPortalType is None:
            return None
        
        defaultView = self._getObjectDefaultView(parent)
        if defaultView == templateName:
            name = ploneCacheSettings.contentTypeRulesetMapping.get(parentPortalType, None)
            if name is not None:
                return name
        
        return None
    
    def _getObjectDefaultView(self, context):
        """Get the id of an object's default view
        """
        
        # courtesy of Producs.CacheSetup
        
        browserDefault = IBrowserDefault(context, None)
        
        if browserDefault is not None:
            try:
                return browserDefault.defaultView()
            except AttributeError:
                # Might happen if FTI didn't migrate yet.
                pass

        fti = context.getTypeInfo()
        try:
            # XXX: This isn't quite right since it assumes the action starts with ${object_url}
            action = fti.getActionInfo('object/view')['url'].split('/')[-1]
        except ValueError:
            # If the action doesn't exist, stop
            return None

        # Try resolving method aliases because we need a real template_id here
        if action:
            action = fti.queryMethodID(action, default = action, context = context)
        else:
            action = fti.queryMethodID('(Default)', default = action, context = context)

        # Strip off leading / and/or @@
        if action and action[0] == '/':
            action = action[1:]
        if action and action.startswith('@@'):
            action = action[2:]
        return action

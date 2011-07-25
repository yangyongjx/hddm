import hddm
from hddm.model import Base
import pymc as pm
from kabuki import Parameter

class HDDMContaminant(Base):
    def __init__(self, *args, **kwargs):
        super(HDDMContaminant, self).__init__(*args, **kwargs)
        self.params = [Parameter('a',True, lower=.5, upper=4.5),
                       Parameter('v',True, lower=-6., upper=6.), 
                       Parameter('t',True, lower=.1, upper=2., init=.1),
                       Parameter('pi',True, lower=1e-3, upper=0.2),
                       Parameter('gamma',True, lower=1e-4, upper=1-1e-4),
                       Parameter('x', False), 
                       Parameter('dummy_gamma',False),
                       Parameter('dummy_pi',False),
                       Parameter('wfpt', False),
                       Parameter('z',True, lower=0., upper=1., init=.5, default=.5, optional=True)]
            
        self.t_min = 0
        self.t_max = max(self.data['rt'])

    def get_rootless_child(self, param, params):
        if param.name == 'wfpt':
            return hddm.likelihoods.WienerSimpleContaminant(param.full_name,
                                                            value=param.data['rt'],
                                                            cont_x=params['x'],
                                                            gamma=params['gamma'],
                                                            v=params['v'],
                                                            t=params['t'],
                                                            a=params['a'],
                                                            z=self.get_node('z', params),
                                                            t_min=self.t_min,
                                                            t_max=self.t_max,
                                                            observed=True)
        elif param.name == 'x':
            return pm.Bernoulli(param.full_name, p=params['pi'], size=len(param.data['rt']), plot=False)
        elif param.name == 'dummy_gamma':
            return pm.Bernoulli(param.full_name, p=params['gamma'], value=[True,False], observed=True)
        elif param.name == 'dummy_pi':
            return pm.Bernoulli(param.full_name, p=params['pi'], value=[True], observed=True)
        else:
            raise KeyError, "Rootless child parameter %s not found" % param.name

    def remove_outliers(self, cutoff=.5):
        data_dep = self._get_data_depend()

        data_out = []
        cont = []
        
        # Find x param
        for param in self.params:
            if param.name == 'x':
                break

        for i, (data, params_dep, dep_name) in enumerate(data_dep):
            dep_name = str(dep_name)
            # Contaminant probability
            print dep_name
            for subj_idx, subj in enumerate(self._subjs):
                data_subj = data[data['subj_idx'] == subj]
                cont_prob = np.mean(param.child_nodes[dep_name][subj_idx].trace(), axis=0)
            
                no_cont = np.where(cont_prob < cutoff)[0]
                cont.append(np.logical_not(no_cont))
                data_out.append(data_subj[no_cont])

        data_all = np.concatenate(data_out)
        data_all['rt'] = np.abs(data_all['rt'])
        
        return data_all, np.concatenate(cont)

class HDDMAntisaccade(Base):
    def __init__(self, data, init=True, **kwargs):
        super(self.__class__, self).__init__(data, **kwargs)
        
        if 'instruct' not in self.data.dtype.names:
            raise AttributeError, 'data has to contain a field name instruct.'

        self.params = [Parameter('v',True, lower=-4, upper=0.),
                       Parameter('v_switch', True, lower=0, upper=4.),
                       Parameter('a', True, lower=1, upper=4.5),
                       Parameter('t', True, lower=0., upper=.5, init=0.1),
                       Parameter('t_switch', True, lower=0.0, upper=1.0, init=0.3),
                       Parameter('T', True, lower=0, upper=.5, init=.1, default=0, optional=True),
                       Parameter('V_switch', True, lower=0, upper=2., default=0, optional=True),
                       Parameter('wfpt', False)]

    def get_rootless_child(self, param, params):
        if param.name == 'wfpt':
            return hddm.likelihoods.WienerAntisaccade(param.full_name,
                                                      value=param.data['rt'],
                                                      instruct=param.data['instruct'],
                                                      v=params['v'],
                                                      v_switch=params['v_switch'],
                                                      V_switch=self.get_node('V_switch',params),
                                                      a=params['a'],
                                                      z=.5,
                                                      t=params['t'],
                                                      t_switch=params['t_switch'],
                                                      T=self.get_node('T',params),
                                                      observed=True)
        else:
            raise TypeError, "Parameter named %s not found." % param.name

class HDDMRegressor(Base):
    def __init__(self, data, effects_on=None, use_root_for_effects=False, **kwargs):
        """Hierarchical Drift Diffusion Model analyses for Cavenagh et al, IP.

        Arguments:
        ==========
        data: structured numpy array containing columns: subj_idx, response, RT, theta, dbs

        Keyword Arguments:
        ==================
        effect_on <list>: theta and dbs effect these DDM parameters.
        depend_on <list>: separate stimulus distributions for these parameters.

        Example:
        ========
        The following will create and fit a model on the dataset data, theta and dbs affect the threshold. For each stimulus,
        there are separate drift parameter, while there is a separate HighConflict and LowConflict threshold parameter. The effect coding type is dummy.

        model = Theta(data, effect_on=['a'], depend_on=['v', 'a'], effect_coding=False, HL_on=['a'])
        model.mcmc()
        """
        if effects_on is None:
            self.effects_on = {'a': 'theta'}
        else:
            self.effects_on = effects_on

        self.use_root_for_effects = use_root_for_effects
        
        super(self.__class__, self).__init__(data, **kwargs)
        
    def get_params(self):
        params = []

        # Add rootless nodes for effects
        for effect_on, col_names in self.effects_on.iteritems():
            if type(col_names) is str or (type(col_names) is list and len(col_names) == 1):
                if type(col_names) is list:
                    col_names = col_names[0]
                params.append(Parameter('e_%s_%s'%(col_names, effect_on), True, lower=-3., upper=3., init=0, no_childs=self.use_root_for_effects))
                params.append(Parameter('error_%s_%s'%(col_names, effect_on), True, lower=0., upper=10., init=0, no_childs=self.use_root_for_effects))
                params.append(Parameter('e_inst_%s_%s'%(col_names, effect_on), 
                                        False,
                                        vars={'col_name':col_names,
                                              'effect_on':effect_on,
                                              'e':'e_%s_%s'%(col_names, effect_on)}))
            elif len(col_names) == 2:
                for col_name in col_names:
                    params.append(Parameter('e_%s_%s'%(col_name, effect_on), True, lower=-3., upper=3., init=0, no_childs=self.use_root_for_effects))
                params.append(Parameter('error_%s_%s'%(col_names, effect_on), True, lower=0, upper=10., init=0, no_childs=self.use_root_for_effects))
                params.append(Parameter('e_inter_%s_%s_%s'%(col_names[0], col_names[1], effect_on), 
                                        True, lower=-3., upper=3., init=0, no_childs=self.use_root_for_effects))
                params.append(Parameter('e_inst_%s_%s_%s'%(col_names[0], col_names[1], effect_on), 
                                        False,
                                        vars={'col_name0': col_names[0],
                                              'col_name1': col_names[1],
                                              'effect_on': effect_on,
                                              'e1':'e_%s_%s'%(col_names[0], effect_on),
                                              'e2':'e_%s_%s'%(col_names[1], effect_on),
                                              'inter':'e_inter_%s_%s_%s'%(col_names[0], col_names[1], effect_on)}))
            else:
                raise NotImplementedError, "Only 1 or 2 regressors allowed per variable."

        params += super(self.__class__, self).get_params()

        return params

    def get_rootless_child(self, param, params):
        """Generate the HDDM."""
        if param.name.startswith('e_inst'):
            if not param.vars.has_key('inter'):
                # No interaction
                if param.vars['effect_on'] == 't':
                    func = effect1_nozero
                else:
                    func = effect1

                return pm.Deterministic(func, param.full_name, param.full_name,
                                        parents={'base': self._get_node(param.vars['effect_on'], params),
                                                 'e1': params[param.vars['e']],
                                                 'data': param.data[param.vars['col_name']]}, trace=False, plot=self.plot_subjs)
            else:
                    
                return pm.Deterministic(effect2, param.full_name, param.full_name,
                                        parents={'base': params[param.vars['effect_on']],
                                                 'e1': params[param.vars['e1']],
                                                 'e2': params[param.vars['e2']],
                                                 'e_inter': params[param.vars['inter']],
                                                 'data_e1': param.data[param.vars['col_name0']],
                                                 'data_e2': param.data[param.vars['col_name1']]}, trace=False)

        for effect_on, col_name in self.effects_on.iteritems():
            if type(col_name) is str:
                params[effect_on] = params['e_inst_%s_%s'%(col_name, effect_on)]
            else:
                params[effect_on] = params['e_inst_%s_%s_%s'%(col_name[0], col_name[1], effect_on)]

        if self.model_type == 'simple':
            model = hddm.likelihoods.WienerSimpleMulti(param.full_name,
                                                       value=param.data['rt'],
                                                       v=params['v'],
                                                       a=params['a'],
                                                       z=self._get_node('z',params),
                                                       t=params['t'],
                                                       multi=self.effects_on.keys(),
                                                       observed=True)
        elif self.model_type == 'full':
            model = hddm.likelihoods.WienerFullMulti(param.full_name,
                                                     value=param.data['rt'],
                                                     v=params['v'],
                                                     V=self._get_node('V', params),
                                                     a=params['a'],
                                                     z=self._get_node('z', params),
                                                     Z=self._get_node('Z', params),
                                                     t=params['t'],
                                                     T=self._get_node('T', params),
                                                     multi=self.effects_on.keys(),
                                                     observed=True)
        return model

def effect1(base, e1, error, data):
    """Effect distribution.
    """
    return base + e1 * data + error

def effect1_nozero(base, e1, error, data):
    """Effect distribution where values <0 will be set to 0.
    """
    value = base + e1 * data + error
    value[value < 0] = 0.
    value[value > .4] = .4
    return value

def effect2(base, e1, e2, e_inter, error, data_e1, data_e2):
    """2-regressor effect distribution
    """
    return base + data_e1*e1 + data_e2*e2 + data_e1*data_e2*e_inter + error
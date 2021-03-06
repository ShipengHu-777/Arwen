import copy
import functools

from numpy.lib.function_base import iterable
from fate_arch.session import computing_session as session
from federatedml.util import LOGGER
from federatedml.ensemble.basic_algorithms.decision_tree.tree_core.decision_tree import DecisionTree
from federatedml.ensemble.basic_algorithms.decision_tree.tree_core.node import Node
from federatedml.feature.fate_element_type import NoneType
from federatedml.protobuf.generated.boosting_tree_model_meta_pb2 import CriterionMeta
from federatedml.protobuf.generated.boosting_tree_model_meta_pb2 import DecisionTreeModelMeta
from federatedml.protobuf.generated.boosting_tree_model_param_pb2 import DecisionTreeModelParam
from federatedml.transfer_variable.transfer_class.hetero_decision_tree_transfer_variable import \
    HeteroDecisionTreeTransferVariable
from federatedml.ensemble.basic_algorithms.decision_tree.tree_core.splitinfo_cipher_compressor import \
    GuestSplitInfoDecompressor, GuestGradHessEncoder
from federatedml.secureprotol import PaillierEncrypt, IterativeAffineEncrypt, encrypt
from federatedml.ensemble.basic_algorithms.decision_tree.tree_core.subsample import goss_sampling
from federatedml.util import consts
import pickle


class HeteroDecisionTreeGuest(DecisionTree):

    def __init__(self, tree_param):
        super(HeteroDecisionTreeGuest, self).__init__(tree_param)

        self.encrypter = None
        self.encrypted_mode_calculator = None
        self.transfer_inst = HeteroDecisionTreeTransferVariable()

        self.sitename = consts.GUEST  # will be modified in self.set_runtime_idx()
        self.complete_secure_tree = False
        self.split_maskdict = {}
        self.missing_dir_maskdict = {}
        self.host_party_idlist = []
        self.compressor = None

        # goss subsample
        self.run_goss = False
        self.top_rate, self.other_rate = 0.2, 0.1  # goss sampling rate

        # cipher compressing
        self.cipher_encoder = None
        self.cipher_decompressor = None
        self.run_cipher_compressing = False
        self.key_length = None
        self.round_decimal = 7
        self.max_sample_weight = 1

        # code version control
        self.new_ver = True

    """
    Node Encode/ Decode
    """

    def encode(self, etype="feature_idx", val=None, nid=None):
        if etype == "feature_idx":
            return val

        if etype == "feature_val":
            self.split_maskdict[nid] = val
            return None

        if etype == "missing_dir":
            self.missing_dir_maskdict[nid] = val
            return None

        raise TypeError("encode type %s is not support!" % (str(etype)))

    @staticmethod
    def decode(dtype="feature_idx", val=None, nid=None, split_maskdict=None, missing_dir_maskdict=None):
        if dtype == "feature_idx":
            return val

        if dtype == "feature_val":
            if nid in split_maskdict:
                return split_maskdict[nid]
            else:
                raise ValueError("decode val %s cause error, can't recognize it!" % (str(val)))

        if dtype == "missing_dir":
            if nid in missing_dir_maskdict:
                return missing_dir_maskdict[nid]
            else:
                raise ValueError("decode val %s cause error, can't recognize it!" % (str(val)))

        return TypeError("decode type %s is not support!" % (str(dtype)))

    """
    Setting
    """

    def set_host_party_idlist(self, id_list):
        self.host_party_idlist = id_list

    def report_init_status(self):

        LOGGER.info('reporting initialization status')
        LOGGER.info('using new version code {}'.format(self.new_ver))
        if self.complete_secure_tree:
            LOGGER.info('running complete secure')
        if self.run_goss:
            LOGGER.info('run goss is {}, top rate is {}, other rate is {}'.format(self.run_goss, self.top_rate,
                                                                                  self.other_rate))
            LOGGER.info('sampled g_h count is {}, total sample num is {}'.format(self.grad_and_hess.count(),
                                                                                 self.data_bin.count()))
        if self.run_cipher_compressing:
            LOGGER.info('running cipher compressing')
            LOGGER.info('round decimal is {}'.format(self.round_decimal))
        LOGGER.info('updated max sample weight is {}'.format(self.max_sample_weight))

        if self.deterministic:
            LOGGER.info('running on deterministic mode')

    def init(self, flowid, runtime_idx, data_bin, bin_split_points, bin_sparse_points, valid_features,
             grad_and_hess,
             encrypter, encrypted_mode_calculator,
             host_party_list,
             complete_secure=False,
             goss_subsample=False,
             top_rate=0.1,
             other_rate=0.2,
             cipher_compressing=False,
             encrypt_key_length=None,
             round_decimal=7,
             max_sample_weight=1,
             new_ver=True):

        super(HeteroDecisionTreeGuest, self).init_data_and_variable(flowid, runtime_idx, data_bin, bin_split_points,
                                                                    bin_sparse_points, valid_features, grad_and_hess)

        self.check_max_split_nodes()

        self.encrypter = encrypter
        self.encrypted_mode_calculator = encrypted_mode_calculator
        self.complete_secure_tree = complete_secure
        self.host_party_idlist = host_party_list

        self.run_goss = goss_subsample
        self.top_rate = top_rate
        self.other_rate = other_rate

        self.run_cipher_compressing = cipher_compressing
        self.key_length = encrypt_key_length
        self.round_decimal = round_decimal
        self.max_sample_weight = max_sample_weight

        if self.run_goss:
            self.goss_sampling()
            self.max_sample_weight = self.max_sample_weight * ((1 - top_rate) / other_rate)

        if self.run_cipher_compressing:
            self.init_compressor()

        self.new_ver = new_ver

        self.report_init_status()

    """
    Encrypt/ Decrypt
    """

    def encrypt(self, val):
        return self.encrypter.encrypt(val)

    def decrypt(self, val):
        return self.encrypter.decrypt(val)

    def get_encrypt_type(self):

        if type(self.encrypter) == PaillierEncrypt:
            return consts.PAILLIER
        elif type(self.encrypter) == IterativeAffineEncrypt:
            return consts.ITERATIVEAFFINE
        else:
            raise ValueError('unknown encrypter type: {}'.format(type(self.encrypter)))

    """
    Node Splitting
    """

    def get_host_sitename(self, host_idx):
        host_party_id = self.host_party_idlist[host_idx]
        host_sitename = ":".join([consts.HOST, str(host_party_id)])
        return host_sitename

    def find_host_split(self, value):

        cur_split_node, encrypted_splitinfo_host = value
        sum_grad = cur_split_node.sum_grad
        sum_hess = cur_split_node.sum_hess

        best_gain = self.min_impurity_split - consts.FLOAT_ZERO
        best_idx = -1

        perform_recorder = {}
        gains = []

        for i in range(len(encrypted_splitinfo_host)):
            sum_grad_l, sum_hess_l = encrypted_splitinfo_host[i]
            sum_grad_l = self.decrypt(sum_grad_l)
            sum_hess_l = self.decrypt(sum_hess_l)
            sum_grad_r = sum_grad - sum_grad_l
            sum_hess_r = sum_hess - sum_hess_l
            gain = self.splitter.split_gain(sum_grad, sum_hess, sum_grad_l,
                                            sum_hess_l, sum_grad_r, sum_hess_r)

            perform_recorder[i] = gain
            gains.append(gain)

            if gain > self.min_impurity_split and gain > best_gain + consts.FLOAT_ZERO:
                best_gain = gain
                best_idx = i

        encrypted_best_gain = self.encrypt(best_gain)
        return best_idx, encrypted_best_gain, best_gain

    def find_best_split_guest_and_host(self, splitinfo_guest_host, need_decrypt=True):

        best_gain_host = self.decrypt(splitinfo_guest_host[1].gain) if need_decrypt else splitinfo_guest_host[1].gain
        best_gain_host_idx = 1
        for i in range(1, len(splitinfo_guest_host)):
            gain_host_i = self.decrypt(splitinfo_guest_host[i].gain) if need_decrypt else splitinfo_guest_host[i].gain
            if best_gain_host < gain_host_i - consts.FLOAT_ZERO:
                best_gain_host = gain_host_i
                best_gain_host_idx = i

        # if merge_host_split_only is True, guest hists is None
        if splitinfo_guest_host[0] is not None and \
                splitinfo_guest_host[0].gain >= best_gain_host - consts.FLOAT_ZERO:
            best_splitinfo = splitinfo_guest_host[0]
        else:
            best_splitinfo = splitinfo_guest_host[best_gain_host_idx]

            # when this node can not be further split, host sum_grad and sum_hess is not an encrypted number but 0
            # so need type checking here
            if need_decrypt:
                best_splitinfo.sum_grad = self.decrypt(best_splitinfo.sum_grad) \
                    if type(best_splitinfo.sum_grad) != int else best_splitinfo.sum_grad
                best_splitinfo.sum_hess = self.decrypt(best_splitinfo.sum_hess) \
                    if type(best_splitinfo.sum_hess) != int else best_splitinfo.sum_hess
                best_splitinfo.gain = best_gain_host

        return best_splitinfo

    def merge_splitinfo(self, splitinfo_guest, splitinfo_host, merge_host_split_only=False, need_decrypt=True):

        LOGGER.info("merging splitinfo, merge_host_split_only is {}".format(merge_host_split_only))

        if merge_host_split_only:
            splitinfo_guest = [None for i in range(len(splitinfo_host[0]))]

        merge_infos = []
        for i in range(len(splitinfo_guest)):
            splitinfo = [splitinfo_guest[i]]
            for j in range(len(splitinfo_host)):
                splitinfo.append(splitinfo_host[j][i])

            merge_infos.append(splitinfo)

        splitinfo_guest_host_table = session.parallelize(merge_infos,
                                                         include_key=False,
                                                         partition=self.data_bin.partitions)

        find_split_func = functools.partial(self.find_best_split_guest_and_host, need_decrypt=need_decrypt)
        best_splitinfo_table = splitinfo_guest_host_table.mapValues(find_split_func)

        best_splitinfos = [None for i in range(len(merge_infos))]
        for _, best_splitinfo in best_splitinfo_table.collect():
            best_splitinfos[_] = best_splitinfo

        return best_splitinfos

    def federated_find_split(self, dep=-1, batch=-1, idx=-1):

        LOGGER.info("federated find split of depth {}, batch {}".format(dep, batch))
        # get flatten split points from hosts
        # [split points from host 1, split point from host 2, .... so on] ???
        encrypted_splitinfo_host = self.sync_encrypted_splitinfo_host(dep, batch, idx=idx)

        for host_idx in range(len(encrypted_splitinfo_host)):

            LOGGER.debug('host sitename is {}'.format(self.get_host_sitename(host_idx)))

            init_gain = self.min_impurity_split - consts.FLOAT_ZERO
            encrypted_init_gain = self.encrypter.encrypt(init_gain)
            # init encrypted gain for every nodes in cur layer
            best_splitinfo_host = [[-1, encrypted_init_gain] for j in range(len(self.cur_to_split_nodes))]
            # init best gain for every nodes in cur layer
            best_gains = [init_gain for j in range(len(self.cur_to_split_nodes))]
            # max split points to compute at a time, to control memory consumption
            max_nodes = max(len(encrypted_splitinfo_host[host_idx][j]) for j in range(len(self.cur_to_split_nodes)))
            # batch split point finding for every cur to split nodes
            for k in range(0, max_nodes, consts.MAX_SPLITINFO_TO_COMPUTE):
                batch_splitinfo_host = [encrypted_splitinfo[k: k + consts.MAX_SPLITINFO_TO_COMPUTE] for encrypted_splitinfo
                                        in encrypted_splitinfo_host[host_idx]]

                encrypted_splitinfo_host_table = session.parallelize(zip(self.cur_to_split_nodes, batch_splitinfo_host),
                                                                     include_key=False,
                                                                     partition=self.data_bin.partitions)

                splitinfos = encrypted_splitinfo_host_table.mapValues(self.find_host_split).collect()

                # update best splitinfo and gain for every cur to split nodes
                for node_idx, splitinfo in splitinfos:

                    if best_splitinfo_host[node_idx][0] == -1:
                        best_splitinfo_host[node_idx] = list(splitinfo[:2])
                        best_gains[node_idx] = splitinfo[2]
                    elif splitinfo[0] != -1 and splitinfo[2] > best_gains[node_idx] + consts.FLOAT_ZERO:
                        best_splitinfo_host[node_idx][0] = k + splitinfo[0]
                        best_splitinfo_host[node_idx][1] = splitinfo[1]
                        best_gains[node_idx] = splitinfo[2]

            if idx != -1:
                self.sync_federated_best_splitinfo_host(best_splitinfo_host, dep, batch, idx)
                break

            self.sync_federated_best_splitinfo_host(best_splitinfo_host, dep, batch, host_idx)

    def get_computing_inst2node_idx(self):
        if self.run_goss:
            inst2node_idx = self.inst2node_idx.join(self.grad_and_hess, lambda x1, x2: x1)
        else:
            inst2node_idx = self.inst2node_idx
        return inst2node_idx

    def compute_best_splits2(self, cur_to_split_nodes, node_map, dep, batch_idx):

        LOGGER.info('solving node batch {}, node num is {}'.format(batch_idx, len(cur_to_split_nodes)))
        inst2node_idx = self.get_computing_inst2node_idx()
        node_sample_count = self.count_node_sample_num(inst2node_idx, node_map)
        LOGGER.debug('sample count is {}'.format(node_sample_count))
        # LOGGER.debug("count of data in compute_best_splits2: {}".format(self.data_with_node_assignments.applyPartitions(lambda kv: len(list(kv))).collect()))
        acc_histograms = self.get_local_histograms(dep, self.data_with_node_assignments, self.grad_and_hess,0,
                                                   node_sample_count, cur_to_split_nodes, node_map, ret='tensor',
                                                   hist_sub=True)

        LOGGER.debug('acc_histograms: {}'.format(acc_histograms))
        LOGGER.debug('acc_histograms\' len: {}, {}, {}'.format(len(acc_histograms), len(acc_histograms[0]), len(acc_histograms[0][0])))
        LOGGER.debug('self.data_bin.partitions: {}'.format(self.data_bin.partitions))

        best_split_info_guest = self.splitter.find_split(acc_histograms, self.valid_features,
                                                         self.data_bin.partitions, self.sitename,
                                                         self.use_missing, self.zero_as_missing)

        if self.complete_secure_tree:
            return best_split_info_guest

        host_split_info_tables = self.transfer_inst.encrypted_splitinfo_host.get(idx=-1, suffix=(dep, batch_idx))

        LOGGER.debug('host_split_info_tables: {}'.format(list(host_split_info_tables[0].collect())))

        best_splits_of_all_hosts = []

        if self.run_cipher_compressing:
            self.cipher_decompressor.renew_decompressor(node_map)
        cipher_decompressor = self.cipher_decompressor if self.run_cipher_compressing else None

        for host_idx, split_info_table in enumerate(host_split_info_tables):

            host_split_info = self.splitter.find_host_best_split_info(split_info_table, self.get_host_sitename(host_idx),
                                                                      self.encrypter,
                                                                      cipher_decompressor=cipher_decompressor)
            split_info_list = [None for i in range(len(host_split_info))]
            for key in host_split_info:
                split_info_list[node_map[key]] = host_split_info[key]
            return_split_info = copy.deepcopy(split_info_list)
            for split_info in return_split_info:
                split_info.sum_grad, split_info.sum_hess, split_info.gain = None, None, None
            self.transfer_inst.federated_best_splitinfo_host.remote(return_split_info,
                                                                    suffix=(dep, batch_idx), idx=host_idx,
                                                                    role=consts.HOST)
            best_splits_of_all_hosts.append(split_info_list)
        
        LOGGER.debug('best_splits_of_all_hosts: {}'.format(list(best_splits_of_all_hosts)))

        # get encoded split-info from hosts
        final_host_split_info = self.sync_final_split_host(dep, batch_idx)

        LOGGER.debug('final_host_split_info: {}'.format(list(final_host_split_info)))

        for masked_split_info, encoded_split_info in zip(best_splits_of_all_hosts, final_host_split_info):
            for s1, s2 in zip(masked_split_info, encoded_split_info):
                s2.gain = s1.gain
                s2.sum_grad = s1.sum_grad
                s2.sum_hess = s1.sum_hess

        final_best_splits = self.merge_splitinfo(best_split_info_guest, final_host_split_info, need_decrypt=False)

        return final_best_splits

    def compute_best_splits(self, cur_to_split_nodes, node_map, dep, batch_idx):

        acc_histograms = self.get_local_histograms(dep, self.data_with_node_assignments, self.grad_and_hess,
                                                   None, cur_to_split_nodes, node_map, ret='tensor',
                                                   hist_sub=False)

        best_split_info_guest = self.splitter.find_split(acc_histograms, self.valid_features,
                                                         self.data_bin.partitions, self.sitename,
                                                         self.use_missing, self.zero_as_missing)
        LOGGER.debug('computing local splits done')

        if self.complete_secure_tree:
            return best_split_info_guest

        self.federated_find_split(dep, batch_idx)
        host_split_info = self.sync_final_split_host(dep, batch_idx)

        # compare host best split points with guest split points
        cur_best_split = self.merge_splitinfo(splitinfo_guest=best_split_info_guest,
                                              splitinfo_host=host_split_info,
                                              merge_host_split_only=False)

        return cur_best_split

    """
    Federation Functions
    """

    def process_and_sync_grad_and_hess(self, idx=-1):
        optimization_none=True
        optimization_1=False
        optimization_2=False

        if optimization_none:
            if self.run_cipher_compressing:
                LOGGER.info('sending encoded g/h to host')
                en_grad_hess = self.cipher_encoder.encode_g_h_and_encrypt(self.grad_and_hess)
            else:
                LOGGER.info('sending g/h to host')
                en_grad_hess = self.encrypted_mode_calculator.encrypt(self.grad_and_hess)

            self.transfer_inst.encrypted_grad_and_hess.remote(en_grad_hess,
                                                          role=consts.HOST,
                                                          idx=idx)
        elif optimization_1:
            g_h_list=list(self.grad_and_hess.collect())
            val_to_idx_first = {}
            val_to_idxs = {}
            val_to_index = {}
            unique_vals={}
            i = 0
            for gh in g_h_list:
                if gh[1] not in val_to_idxs:
                    val_to_idx_first[gh[1]] = gh[0]
                    val_to_idxs[gh[1]] = [gh[0]]

                    unique_vals[gh[1]] = i
                    val_to_index[gh[0]] = i
                else:
                    val_to_idxs[gh[1]].append(gh[0])

                    val_to_index[gh[0]] = unique_vals[gh[1]]
                i += 1
            compressed_gh = self.grad_and_hess.filter(lambda k, v: val_to_idx_first[v] == k)
            val_to_index_table = self.grad_and_hess.map(lambda k, v: (k, val_to_index[k]))
            val_to_index_table = val_to_index_table.subtractByKey(compressed_gh)
            if self.run_cipher_compressing:
                LOGGER.info('sending encoded g/h to host')
                en_grad_hess = self.cipher_encoder.encode_g_h_and_encrypt(compressed_gh)
            else:
                LOGGER.info('sending g/h to host')
                en_grad_hess = self.encrypted_mode_calculator.encrypt(compressed_gh)
            self.transfer_inst.encrypted_grad_and_hess.remote(en_grad_hess.union(val_to_index_table, lambda k, v : 1),
                                                          role=consts.HOST,
                                                          idx=idx)
        elif optimization_2:
            g_h_list=list(self.grad_and_hess.collect())
            unique_vals=[]
            id_to_valindex={}
            val_to_idx_first = {}
            for gh in g_h_list:
                if gh[1] not in unique_vals:
                    unique_vals.append(gh[1])
                    val_to_idx_first[gh[1]] = gh[0]
                id_to_valindex[gh[0]]=unique_vals.index(gh[1])
            compressed_gh = (self.grad_and_hess.filter(lambda k, v: val_to_idx_first[v] == k)).map(lambda k, v: ((-1)*(unique_vals.index(v)+1),v))
            en_grad_hess = (self.cipher_encoder.encode_g_h_and_encrypt(compressed_gh)).mapValues(lambda v: [v])
            
            # LOGGER.debug('raw_gh is {}'.format(g_h_list))

            #LOGGER.debug('compressed_gh is {}'.format(list(compressed_gh.collect())))
            #LOGGER.debug('list en_grad_hess is {}'.format(list(en_grad_hess.collect())))
            # for i in range(9):
            #     compressed_gh=compressed_gh.mapValues(lambda v: (v[0]+v[0],v[1]+v[1]))
            #     en_grad_hess=en_grad_hess.join(self.cipher_encoder.encode_g_h_and_encrypt(compressed_gh),lambda v1, v2: v1 if v1.append(v2) else v1)
            id_to_index_table=self.grad_and_hess.map(lambda k, v: (k,id_to_valindex[k]))
            #LOGGER.debug('id_to_index_table is {}'.format(list(id_to_index_table.collect())))
            #LOGGER.debug('en_grad_hess is {}'.format(list(en_grad_hess.collect())))
            self.transfer_inst.encrypted_grad_and_hess.remote(en_grad_hess.union(id_to_index_table,lambda k,v:1),
                                                            role=consts.HOST,
                                                            idx=idx)





    def sync_cur_to_split_nodes(self, cur_to_split_node, dep=-1, idx=-1):
        LOGGER.info("send tree node queue of depth {}".format(dep))
        mask_tree_node_queue = copy.deepcopy(cur_to_split_node)
        for i in range(len(mask_tree_node_queue)):
            mask_tree_node_queue[i] = Node(id=mask_tree_node_queue[i].id,
                                           parent_nodeid=mask_tree_node_queue[i].parent_nodeid,
                                           is_left_node=mask_tree_node_queue[i].is_left_node,)
        LOGGER.debug('cur_to_split_node: {}'.format(map(lambda x: str(x), cur_to_split_node)))
        LOGGER.debug('mask_tree_node_queue: {}'.format(map(lambda x: str(x), mask_tree_node_queue)))

        self.transfer_inst.tree_node_queue.remote(mask_tree_node_queue,
                                                  role=consts.HOST,
                                                  idx=idx,
                                                  suffix=(dep,))

    def sync_node_positions(self, dep, idx=-1):
        LOGGER.info("send node positions of depth {}".format(dep))
        self.transfer_inst.node_positions.remote(self.inst2node_idx,
                                                 role=consts.HOST,
                                                 idx=idx,
                                                 suffix=(dep,))

    def sync_encrypted_splitinfo_host(self, dep=-1, batch=-1, idx=-1):
        LOGGER.info("get encrypted splitinfo of depth {}, batch {}".format(dep, batch))

        LOGGER.debug('host idx is {}'.format(idx))
        encrypted_splitinfo_host = self.transfer_inst.encrypted_splitinfo_host.get(idx=idx,
                                                                                   suffix=(dep, batch,))
        ret = []
        if idx == -1:
            for obj in encrypted_splitinfo_host:
                ret.append(obj.get_data())
        else:
            ret.append(encrypted_splitinfo_host.get_data())

        return ret

    def sync_federated_best_splitinfo_host(self, federated_best_splitinfo_host, dep=-1, batch=-1, idx=-1):
        LOGGER.info("send federated best splitinfo of depth {}, batch {}".format(dep, batch))
        self.transfer_inst.federated_best_splitinfo_host.remote(federated_best_splitinfo_host,
                                                                role=consts.HOST,
                                                                idx=idx,
                                                                suffix=(dep, batch,))

    def sync_final_split_host(self, dep=-1, batch=-1, idx=-1):
        LOGGER.info("get host final splitinfo of depth {}, batch {}".format(dep, batch))
        final_splitinfo_host = self.transfer_inst.final_splitinfo_host.get(idx=idx,
                                                                           suffix=(dep, batch,))
        return final_splitinfo_host if idx == -1 else [final_splitinfo_host]

    def sync_dispatch_node_host(self, dispatch_guest_data, dep=-1, idx=-1):

        LOGGER.info("send node to host to dispatch, depth is {}".format(dep))
        self.transfer_inst.dispatch_node_host.remote(dispatch_guest_data,
                                                     role=consts.HOST,
                                                     idx=idx,
                                                     suffix=(dep,))
        LOGGER.info("get host dispatch result, depth is {}".format(dep))
        ret = self.transfer_inst.dispatch_node_host_result.get(idx=idx, suffix=(dep,))
        return ret if idx == -1 else [ret]

    def sync_tree(self, idx=-1):
        LOGGER.info("sync tree to host")
        tree_nodes = self.remove_sensitive_info()
        self.transfer_inst.tree.remote(tree_nodes,
                                       role=consts.HOST,
                                       idx=idx)

    def sync_predict_finish_tag(self, finish_tag, send_times):
        LOGGER.info("send the {}-th predict finish tag {} to host".format(finish_tag, send_times))

        self.transfer_inst.predict_finish_tag.remote(finish_tag,
                                                     role=consts.HOST,
                                                     idx=-1,
                                                     suffix=(send_times,))

    def sync_predict_data(self, predict_data, send_times):
        LOGGER.info("send predict data to host, sending times is {}".format(send_times))
        self.transfer_inst.predict_data.remote(predict_data,
                                               role=consts.HOST,
                                               idx=-1,
                                               suffix=(send_times,))

    def sync_data_predicted_by_host(self, send_times):
        LOGGER.info("get predicted data by host, recv times is {}".format(send_times))
        predict_data = self.transfer_inst.predict_data_by_host.get(idx=-1,
                                                                   suffix=(send_times,))
        return predict_data

    """
    Pre-porcess / Post-Process
    """

    def init_compressor(self):

        self.cipher_encoder = GuestGradHessEncoder(self.encrypter, self.encrypted_mode_calculator, task_type=consts.CLASSIFICATION,
                                                   round_decimal=self.round_decimal, max_sample_weights=self.max_sample_weight)

        self.cipher_decompressor = GuestSplitInfoDecompressor(self.encrypter, task_type=consts.CLASSIFICATION,
                                                              max_sample_weight=self.max_sample_weight)

        max_capacity_int = self.encrypter.public_key.max_int
        para = {'max_capacity_int': max_capacity_int, 'en_type': self.get_encrypt_type(),
                'max_sample_weight': self.max_sample_weight}

        self.transfer_inst.cipher_compressor_para.remote(para, idx=-1)

    def goss_sampling(self,):
        new_g_h = goss_sampling(self.grad_and_hess, self.top_rate, self.other_rate)
        self.grad_and_hess = new_g_h

    def remove_sensitive_info(self):
        """
        host is not allowed to get weights/g/h
        """
        new_tree_ = copy.deepcopy(self.tree_node)
        for node in new_tree_:
            node.weight = None
            node.sum_grad = None
            node.sum_hess = None

        return new_tree_

    def initialize_root_node(self,):
        LOGGER.info('initializing root node')
        root_sum_grad, root_sum_hess = self.get_grad_hess_sum(self.grad_and_hess)
        root_node = Node(id=0, sitename=self.sitename, sum_grad=root_sum_grad, sum_hess=root_sum_hess,
                         weight=self.splitter.node_weight(root_sum_grad, root_sum_hess))
        return root_node

    def convert_bin_to_real(self):
        LOGGER.info("convert tree node bins to real value")
        for i in range(len(self.tree_node)):
            if self.tree_node[i].is_leaf is True:
                continue
            if self.tree_node[i].sitename == self.sitename:
                fid = self.decode("feature_idx", self.tree_node[i].fid, split_maskdict=self.split_maskdict)
                bid = self.decode("feature_val", self.tree_node[i].bid, self.tree_node[i].id, self.split_maskdict)
                real_split_val = self.encode("feature_val", self.bin_split_points[fid][bid], self.tree_node[i].id)
                self.tree_node[i].bid = real_split_val

    """
    Tree Updating
    """

    def update_tree(self, split_info, reach_max_depth):

        LOGGER.info("update tree node, splitlist length is {}, tree node queue size is".format(
            len(split_info), len(self.cur_layer_nodes)))
        new_tree_node_queue = []
        for i in range(len(self.cur_layer_nodes)):
            sum_grad = self.cur_layer_nodes[i].sum_grad
            sum_hess = self.cur_layer_nodes[i].sum_hess
            if reach_max_depth or split_info[i].gain <= \
                    self.min_impurity_split + consts.FLOAT_ZERO:  # if reach max_depth, only convert nodes to leaves
                self.cur_layer_nodes[i].is_leaf = True
            else:
                pid = self.cur_layer_nodes[i].id
                self.cur_layer_nodes[i].left_nodeid = self.tree_node_num + 1
                self.cur_layer_nodes[i].right_nodeid = self.tree_node_num + 2
                self.tree_node_num += 2

                left_node = Node(id=self.cur_layer_nodes[i].left_nodeid,
                                 sitename=self.sitename,
                                 sum_grad=split_info[i].sum_grad,
                                 sum_hess=split_info[i].sum_hess,
                                 weight=self.splitter.node_weight(split_info[i].sum_grad, split_info[i].sum_hess),
                                 is_left_node=True,
                                 parent_nodeid=pid)

                right_node = Node(id=self.cur_layer_nodes[i].right_nodeid,
                                  sitename=self.sitename,
                                  sum_grad=sum_grad - split_info[i].sum_grad,
                                  sum_hess=sum_hess - split_info[i].sum_hess,
                                  weight=self.splitter.node_weight(
                                      sum_grad - split_info[i].sum_grad,
                                      sum_hess - split_info[i].sum_hess),
                                  is_left_node=False,
                                  parent_nodeid=pid)

                new_tree_node_queue.append(left_node)
                new_tree_node_queue.append(right_node)

                self.cur_layer_nodes[i].sitename = split_info[i].sitename
                if self.cur_layer_nodes[i].sitename == self.sitename:
                    self.cur_layer_nodes[i].fid = self.encode("feature_idx", split_info[i].best_fid)
                    self.cur_layer_nodes[i].bid = self.encode("feature_val", split_info[i].best_bid,
                                                              self.cur_layer_nodes[i].id)
                    self.cur_layer_nodes[i].missing_dir = self.encode("missing_dir",
                                                                      split_info[i].missing_dir,
                                                                      self.cur_layer_nodes[i].id)
                else:
                    self.cur_layer_nodes[i].fid = split_info[i].best_fid
                    self.cur_layer_nodes[i].bid = split_info[i].best_bid

                self.update_feature_importance(split_info[i])

            self.tree_node.append(self.cur_layer_nodes[i])

        self.cur_layer_nodes = new_tree_node_queue

    @staticmethod
    def assign_an_instance(value, tree_=None, decoder=None, sitename=consts.GUEST,
                           split_maskdict=None, bin_sparse_points=None,
                           use_missing=False, zero_as_missing=False,
                           missing_dir_maskdict=None):

        unleaf_state, nodeid = value[1]

        if tree_[nodeid].is_leaf is True:
            return tree_[nodeid].weight
        else:
            if tree_[nodeid].sitename == sitename:
                fid = decoder("feature_idx", tree_[nodeid].fid, split_maskdict=split_maskdict)
                bid = decoder("feature_val", tree_[nodeid].bid, nodeid, split_maskdict=split_maskdict)
                if not use_missing:
                    if value[0].features.get_data(fid, bin_sparse_points[fid]) <= bid:
                        return 1, tree_[nodeid].left_nodeid
                    else:
                        return 1, tree_[nodeid].right_nodeid
                else:
                    missing_dir = decoder("missing_dir", tree_[nodeid].missing_dir, nodeid,
                                          missing_dir_maskdict=missing_dir_maskdict)

                    missing_val = False
                    if zero_as_missing:
                        if value[0].features.get_data(fid, None) is None or \
                                value[0].features.get_data(fid) == NoneType():
                            missing_val = True
                    elif use_missing and value[0].features.get_data(fid) == NoneType():
                        missing_val = True

                    if missing_val:
                        if missing_dir == 1:
                            return 1, tree_[nodeid].right_nodeid
                        else:
                            return 1, tree_[nodeid].left_nodeid
                    else:
                        LOGGER.debug("fid is {}, bid is {}, sitename is {}".format(fid, bid, sitename))
                        if value[0].features.get_data(fid, bin_sparse_points[fid]) <= bid:
                            return 1, tree_[nodeid].left_nodeid
                        else:
                            return 1, tree_[nodeid].right_nodeid
            else:
                return (1, tree_[nodeid].fid, tree_[nodeid].bid, tree_[nodeid].sitename,
                        nodeid, tree_[nodeid].left_nodeid, tree_[nodeid].right_nodeid)

    def assign_instances_to_new_node(self, dep, reach_max_depth=False):

        LOGGER.info("redispatch node of depth {}".format(dep))
        dispatch_node_method = functools.partial(self.assign_an_instance,
                                                 tree_=self.tree_node,
                                                 decoder=self.decode,
                                                 sitename=self.sitename,
                                                 split_maskdict=self.split_maskdict,
                                                 bin_sparse_points=self.bin_sparse_points,
                                                 use_missing=self.use_missing,
                                                 zero_as_missing=self.zero_as_missing,
                                                 missing_dir_maskdict=self.missing_dir_maskdict)

        dispatch_guest_result = self.data_with_node_assignments.mapValues(dispatch_node_method)
        LOGGER.info("remask dispatch node result of depth {}".format(dep))

        dispatch_to_host_result = dispatch_guest_result.filter(
            lambda key, value: isinstance(value, tuple) and len(value) > 2)

        dispatch_guest_result = dispatch_guest_result.subtractByKey(dispatch_to_host_result)
        leaf = dispatch_guest_result.filter(lambda key, value: isinstance(value, tuple) is False)

        if self.sample_weights is None:
            self.sample_weights = leaf
        else:
            self.sample_weights = self.sample_weights.union(leaf)

        if reach_max_depth:  # if reach max_depth only update weight samples
            return

        dispatch_guest_result = dispatch_guest_result.subtractByKey(leaf)
        dispatch_node_host_result = self.sync_dispatch_node_host(dispatch_to_host_result, dep)

        self.inst2node_idx = None
        for idx in range(len(dispatch_node_host_result)):
            if self.inst2node_idx is None:
                self.inst2node_idx = dispatch_node_host_result[idx]
            else:
                self.inst2node_idx = self.inst2node_idx.join(dispatch_node_host_result[idx],
                                                             lambda unleaf_state_nodeid1, unleaf_state_nodeid2:
                                                             unleaf_state_nodeid1 if len(
                                                             unleaf_state_nodeid1) == 2 else unleaf_state_nodeid2)

        self.inst2node_idx = self.inst2node_idx.union(dispatch_guest_result)

    def assign_instance_to_leaves_and_update_weights(self):
        # re-assign samples to leaf nodes and update weights
        self.update_tree([], True)
        self.update_instances_node_positions()
        self.assign_instances_to_new_node(self.max_depth, reach_max_depth=True)

    def update_instances_node_positions(self):
        self.data_with_node_assignments = self.data_bin.join(self.inst2node_idx, lambda data_inst, dispatch_info: (
            data_inst, dispatch_info))

    """
    Fit & Predict
    """

    def fit(self):

        LOGGER.info('fitting a guest decision tree')

        self.process_and_sync_grad_and_hess()
        root_node = self.initialize_root_node()
        self.cur_layer_nodes = [root_node]
        self.inst2node_idx = self.assign_instance_to_root_node(self.data_bin, root_node_id=root_node.id)


        for dep in range(self.max_depth):
            LOGGER.info('At dep {}, cur layer has {} nodes'.format(dep, len(self.cur_layer_nodes)))

            self.sync_cur_to_split_nodes(self.cur_layer_nodes, dep)
            if len(self.cur_layer_nodes) == 0:
                break

            self.sync_node_positions(dep)
            self.update_instances_node_positions()


            split_info = []
            for batch_idx, i in enumerate(range(0, len(self.cur_layer_nodes), self.max_split_nodes)):
                
                self.cur_to_split_nodes = self.cur_layer_nodes[i: i + self.max_split_nodes]
                node_map = self.get_node_map(self.cur_to_split_nodes)
                if self.new_ver:
                    cur_splitinfos = self.compute_best_splits2(self.cur_to_split_nodes, node_map, dep, batch_idx)
                else:
                    cur_splitinfos = self.compute_best_splits(self.cur_to_split_nodes, node_map, dep, batch_idx)
                
                split_info.extend(cur_splitinfos)
                

            self.update_tree(split_info, False)
            self.assign_instances_to_new_node(dep)
            
    
       
        if self.cur_layer_nodes:
            self.assign_instance_to_leaves_and_update_weights()
        
        self.convert_bin_to_real()
        
        self.round_leaf_val()
       
        self.sync_tree()
        
        LOGGER.info("fitting guest decision tree done")

    @staticmethod
    def traverse_tree(predict_state, data_inst, tree_=None,
                      decoder=None, sitename=consts.GUEST, split_maskdict=None,
                      use_missing=None, zero_as_missing=None, missing_dir_maskdict=None, return_leaf_id=False):

        nid, tag = predict_state

        while tree_[nid].sitename == sitename:
            if tree_[nid].is_leaf is True:
                return tree_[nid].weight if not return_leaf_id else nid

            fid = decoder("feature_idx", tree_[nid].fid, split_maskdict=split_maskdict)
            bid = decoder("feature_val", tree_[nid].bid, nid, split_maskdict=split_maskdict)
            if use_missing:
                missing_dir = decoder("missing_dir", 1, nid, missing_dir_maskdict=missing_dir_maskdict)
            else:
                missing_dir = 1

            if use_missing and zero_as_missing:
                missing_dir = decoder("missing_dir", 1, nid, missing_dir_maskdict=missing_dir_maskdict)
                if data_inst.features.get_data(fid) == NoneType() or data_inst.features.get_data(fid, None) is None:
                    if missing_dir == 1:
                        nid = tree_[nid].right_nodeid
                    else:
                        nid = tree_[nid].left_nodeid
                elif data_inst.features.get_data(fid) <= bid + consts.FLOAT_ZERO:
                    nid = tree_[nid].left_nodeid
                else:
                    nid = tree_[nid].right_nodeid
            elif data_inst.features.get_data(fid) == NoneType():
                if missing_dir == 1:
                    nid = tree_[nid].right_nodeid
                else:
                    nid = tree_[nid].left_nodeid
            elif data_inst.features.get_data(fid, 0) <= bid + consts.FLOAT_ZERO:
                nid = tree_[nid].left_nodeid
            else:
                nid = tree_[nid].right_nodeid

        return nid, 1

    def predict(self, data_inst):

        LOGGER.info("start to predict!")
        predict_data = data_inst.mapValues(lambda inst: (0, 1))
        site_host_send_times = 0
        predict_result = None

        while True:
            traverse_tree = functools.partial(self.traverse_tree,
                                              tree_=self.tree_node,
                                              decoder=self.decode,
                                              sitename=self.sitename,
                                              split_maskdict=self.split_maskdict,
                                              use_missing=self.use_missing,
                                              zero_as_missing=self.zero_as_missing,
                                              missing_dir_maskdict=self.missing_dir_maskdict,
                                              return_leaf_id=False)

            predict_data = predict_data.join(data_inst, traverse_tree)
            predict_leaf = predict_data.filter(lambda key, value: isinstance(value, tuple) is False)
            if predict_result is None:
                predict_result = predict_leaf
            else:
                predict_result = predict_result.union(predict_leaf)

            predict_data = predict_data.subtractByKey(predict_leaf)
            unleaf_node_count = predict_data.count()

            if unleaf_node_count == 0:
                self.sync_predict_finish_tag(True, site_host_send_times)
                break

            self.sync_predict_finish_tag(False, site_host_send_times)
            self.sync_predict_data(predict_data, site_host_send_times)

            predict_data_host = self.sync_data_predicted_by_host(site_host_send_times)
            for i in range(len(predict_data_host)):
                predict_data = predict_data.join(predict_data_host[i],
                                                 lambda state1_nodeid1, state2_nodeid2:
                                                 state1_nodeid1 if state1_nodeid1[
                                                                       1] == 0 else state2_nodeid2)

            site_host_send_times += 1

        LOGGER.info("predict finish!")
        return predict_result

    """
    Tree output
    """

    def get_model_meta(self):

        model_meta = DecisionTreeModelMeta()
        model_meta.criterion_meta.CopyFrom(CriterionMeta(criterion_method=self.criterion_method,
                                                         criterion_param=self.criterion_params))

        model_meta.max_depth = self.max_depth
        model_meta.min_sample_split = self.min_sample_split
        model_meta.min_impurity_split = self.min_impurity_split
        model_meta.min_leaf_node = self.min_leaf_node
        model_meta.use_missing = self.use_missing
        model_meta.zero_as_missing = self.zero_as_missing

        return model_meta

    def set_model_meta(self, model_meta):
        self.max_depth = model_meta.max_depth
        self.min_sample_split = model_meta.min_sample_split
        self.min_impurity_split = model_meta.min_impurity_split
        self.min_leaf_node = model_meta.min_leaf_node
        self.criterion_method = model_meta.criterion_meta.criterion_method
        self.criterion_params = list(model_meta.criterion_meta.criterion_param)
        self.use_missing = model_meta.use_missing
        self.zero_as_missing = model_meta.zero_as_missing

    def get_model_param(self):

        model_param = DecisionTreeModelParam()
        for node in self.tree_node:
            model_param.tree_.add(id=node.id,
                                  sitename=node.sitename,
                                  fid=node.fid,
                                  bid=node.bid,
                                  weight=node.weight,
                                  is_leaf=node.is_leaf,
                                  left_nodeid=node.left_nodeid,
                                  right_nodeid=node.right_nodeid,
                                  missing_dir=node.missing_dir)

        model_param.split_maskdict.update(self.split_maskdict)
        model_param.missing_dir_maskdict.update(self.missing_dir_maskdict)

        return model_param

    def set_model_param(self, model_param):
        self.tree_node = []
        for node_param in model_param.tree_:
            _node = Node(id=node_param.id,
                         sitename=node_param.sitename,
                         fid=node_param.fid,
                         bid=node_param.bid,
                         weight=node_param.weight,
                         is_leaf=node_param.is_leaf,
                         left_nodeid=node_param.left_nodeid,
                         right_nodeid=node_param.right_nodeid,
                         missing_dir=node_param.missing_dir)

            self.tree_node.append(_node)

        self.split_maskdict = dict(model_param.split_maskdict)
        self.missing_dir_maskdict = dict(model_param.missing_dir_maskdict)

